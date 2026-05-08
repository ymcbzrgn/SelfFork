"""HybridRetriever — adaptive hybrid retrieval over a :class:`MindStore`.

Per ADR-002 §5: vector + BM25 + tag-boost fusion with adaptive routing
(graph routing stub lands Order 4 with HippoRAG 2 PPR). Every recall
emits a :class:`ProvenanceEntry` so the dashboard's Sources surface has
ground truth (ADR-002 §8).

Pipeline:

1. Optionally embed the query (when an embedder is wired).
2. Ask the store for ``top_k * rerank_overfetch`` candidates honouring
   filter/scope/tag-match/bi-temporal/path-scope.
3. Pre-fetch each candidate's tag set so the tag-boost scorer can do
   its job and score normalisation has a stable corpus.
4. Run the convex-fusion scorer over (semantic, BM25, tag boost) and
   sort.
5. Apply the optional reranker to the top ``top_k * rerank_overfetch``
   candidates (cross-encoder rerank → final ordering).
6. Apply the threshold cut.
7. Record provenance (best-effort — never fails the recall path).
8. Return the top-``k`` :class:`RetrievalHit`s.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from selffork_mind.memory.filters import Filter
from selffork_mind.memory.model import TierName
from selffork_mind.memory.tags import TagMatchMode
from selffork_mind.projections.provenance import (
    ProvenanceEntry,
    ProvenanceRecorder,
)
from selffork_mind.rag.embedder import EmbeddingProvider
from selffork_mind.rag.reranker import RerankerProvider
from selffork_mind.rag.scoring import (
    ConvexFusionScorer,
    Scorer,
)
from selffork_mind.store.base import (
    MindStore,
    RetrievalHit,
    RetrieveConfig,
    StoreScope,
)

__all__ = [
    "HybridRetriever",
    "QueryRoute",
    "classify_query",
]


QueryRoute = Literal["vector", "graph", "hybrid"]
"""Routing label produced by :func:`classify_query`.

``vector`` — single-fact / semantic similarity. Default route in Order 2.
``graph`` — multi-hop / temporal / causal. Stub label until Order 4.
``hybrid`` — blend of both (vector primary, graph signal layered).
"""


_TEMPORAL_HINTS: tuple[str, ...] = (
    "when ",
    "before",
    "after",
    "earlier",
    "previous",
    "supersede",
    "yesterday",
    "last",
    "between",
    "ne zaman",
    "önce",
    "sonra",
    "geçen",
    "dün",
)


def classify_query(query: str) -> QueryRoute:
    """Heuristic query classifier — vector vs graph vs hybrid.

    Order 2 only ships the vector route end-to-end; graph is a stub.
    The classifier still returns the correct label so audit logs and
    provenance traces describe what *would* have run when the graph
    backend lands in Order 4.
    """
    text = query.lower()
    if any(hint in text for hint in _TEMPORAL_HINTS):
        return "hybrid"
    return "vector"


@dataclass(frozen=True, slots=True)
class _CandidateBundle:
    hits: list[RetrievalHit]
    """Store hits BEFORE fusion. Score field carries the store's vector cosine."""

    tag_pairs_per_note: dict[UUID, set[tuple[str, str]]]


class HybridRetriever:
    """Hybrid retriever over a :class:`MindStore` with provenance.

    Construct once per Mind session (or once per orchestrator process —
    the retriever holds no per-session state). Each :meth:`recall` call
    is independent.
    """

    def __init__(
        self,
        *,
        store: MindStore,
        embedder: EmbeddingProvider | None = None,
        reranker: RerankerProvider | None = None,
        provenance: ProvenanceRecorder | None = None,
        scorer: Scorer | None = None,
        graph_retriever: object | None = None,
        graph_alpha: float = 0.4,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._reranker = reranker
        self._provenance = provenance
        self._scorer: Scorer = scorer or ConvexFusionScorer.build_default()
        self._graph_retriever = graph_retriever
        self._graph_alpha = graph_alpha

    @property
    def embedder(self) -> EmbeddingProvider | None:
        return self._embedder

    @property
    def reranker(self) -> RerankerProvider | None:
        return self._reranker

    async def recall(
        self,
        *,
        query: str,
        scope: StoreScope | None = None,
        tiers: tuple[TierName, ...] = (),
        top_k: int = 10,
        threshold: float = 0.0,
        filter: Filter | None = None,
        tag_pairs: tuple[tuple[str, str], ...] = (),
        tag_match_mode: TagMatchMode = TagMatchMode.ANY,
        rerank_overfetch: int = 4,
        file_path: str | None = None,
        valid_at: datetime | None = None,
        correlation_id: str | None = None,
        session_id: str | None = None,
        project_slug: str | None = None,
    ) -> list[RetrievalHit]:
        """Run a recall. See module docstring for the pipeline."""
        scope_value = scope if scope is not None else StoreScope()
        route = classify_query(query)

        query_embedding: tuple[float, ...] | None = None
        if self._embedder is not None and query.strip():
            embedded = await self._embedder.embed_query(query)
            query_embedding = tuple(float(x) for x in embedded)

        bundle = await self._fetch_candidates(
            query=query,
            query_embedding=query_embedding,
            scope=scope_value,
            tiers=tiers,
            filter=filter,
            tag_pairs=tag_pairs,
            tag_match_mode=tag_match_mode,
            top_k=top_k,
            rerank_overfetch=rerank_overfetch,
            valid_at=valid_at,
            file_path=file_path,
        )

        # Score the vector candidates (may be empty — handled below).
        per_note_vector: dict[UUID, float] = {h.note.id: h.score for h in bundle.hits}
        candidates = [h.note for h in bundle.hits]
        fused: dict[UUID, float]
        if candidates:
            fused = self._scorer.score(
                query=query,
                query_embedding=query_embedding,
                candidates=candidates,
                per_note_vector_score=per_note_vector,
                tag_pairs=tag_pairs,
                tag_pairs_per_note=bundle.tag_pairs_per_note,
            )
        else:
            fused = {}
        fused_hits = [RetrievalHit(note=n, score=fused.get(n.id, 0.0)) for n in candidates]

        # Graph routing — when a graph retriever is wired AND the query
        # classifies as multi-hop / hybrid, blend graph PPR scores into
        # the fused vector. Graph hits not in the candidate set are
        # appended; the final sort + threshold still gates them.
        if self._graph_retriever is not None and route in {"graph", "hybrid"}:
            graph_hits = await self._graph_retriever.recall(  # type: ignore[attr-defined]
                query=query,
                top_k=top_k * max(1, rerank_overfetch),
            )
            fused_hits = _blend_graph_hits(
                vector_hits=fused_hits,
                graph_hits=graph_hits,
                graph_alpha=self._graph_alpha,
            )

        fused_hits.sort(key=lambda h: h.score, reverse=True)

        # Optional rerank stage (cross-encoder over top candidates).
        if self._reranker is not None:
            limit = top_k * max(1, rerank_overfetch)
            head = fused_hits[:limit]
            tail = fused_hits[limit:]
            reranked_head = await self._rerank(query=query, hits=head)
            fused_hits = reranked_head + tail

        # Threshold cut + final top-k.
        cut_hits = [h for h in fused_hits if h.score >= threshold]
        final_hits = cut_hits[:top_k]

        await self._record_provenance(
            query=query,
            hits=final_hits,
            route=route,
            correlation_id=correlation_id,
            session_id=session_id,
            project_slug=project_slug,
        )
        return final_hits

    # ── internals ──────────────────────────────────────────────────────

    async def _fetch_candidates(
        self,
        *,
        query: str,
        query_embedding: tuple[float, ...] | None,
        scope: StoreScope,
        tiers: tuple[TierName, ...],
        filter: Filter | None,
        tag_pairs: tuple[tuple[str, str], ...],
        tag_match_mode: TagMatchMode,
        top_k: int,
        rerank_overfetch: int,
        valid_at: datetime | None,
        file_path: str | None,
    ) -> _CandidateBundle:
        del query  # filter-only path; query is consumed by the scorer downstream
        config = RetrieveConfig(
            tiers=tiers,
            scope=scope,
            filter=filter,
            tag_pairs=tag_pairs,
            tag_match_mode=tag_match_mode,
            query_embedding=query_embedding,
            top_k=top_k,
            rerank_overfetch=max(1, rerank_overfetch),
            valid_at=valid_at,
            file_path=file_path,
        )
        hits = await self._store.retrieve(config)

        tag_pairs_per_note: dict[UUID, set[tuple[str, str]]] = {}
        for h in hits:
            attached = await self._store.list_tags(h.note.id)
            tag_pairs_per_note[h.note.id] = {(t.key, t.value) for t in attached}
        return _CandidateBundle(hits=list(hits), tag_pairs_per_note=tag_pairs_per_note)

    async def _rerank(
        self,
        *,
        query: str,
        hits: list[RetrievalHit],
    ) -> list[RetrievalHit]:
        if not hits or self._reranker is None:
            return hits
        documents = [h.note.content for h in hits]
        rerank_scores = await self._reranker.rerank(query, documents)
        # ``rerank`` returns parallel scores; replace the fusion score and resort.
        replaced = [
            RetrievalHit(note=h.note, score=float(s))
            for h, s in zip(hits, rerank_scores, strict=True)
        ]
        replaced.sort(key=lambda h: h.score, reverse=True)
        return replaced

    async def _record_provenance(
        self,
        *,
        query: str,
        hits: Sequence[RetrievalHit],
        route: QueryRoute,
        correlation_id: str | None,
        session_id: str | None,
        project_slug: str | None,
    ) -> None:
        if self._provenance is None:
            return
        retriever_id = self._build_retriever_id(route)
        entry = ProvenanceEntry(
            # Non-empty sentinels so the dashboard "Sources" surface can
            # distinguish "anonymous CLI recall" from "field forgotten"
            # (Order 5 audit Finding #7).
            correlation_id=correlation_id or "anonymous",
            session_id=session_id or "anonymous",
            project_slug=project_slug,
            query=query,
            note_ids=tuple(h.note.id for h in hits),
            scores=tuple(float(h.score) for h in hits),
            retriever=retriever_id,
            reranker=self._reranker.name if self._reranker is not None else None,
        )
        await self._provenance.record(entry)

    def _build_retriever_id(self, route: QueryRoute) -> str:
        embedder_name = self._embedder.name if self._embedder is not None else "none"
        graph_tag = "+graph" if self._graph_retriever is not None else ""
        return f"{route}:{embedder_name}{graph_tag}"


def _blend_graph_hits(
    *,
    vector_hits: list[RetrievalHit],
    graph_hits: Sequence[object],
    graph_alpha: float,
) -> list[RetrievalHit]:
    """Convex-blend graph PPR scores into the vector hits.

    Both score families are min-max normalised first so ``graph_alpha``
    has meaningful magnitude (the graph's raw scores live on different
    scales than the fusion's). Notes that appear only in graph hits are
    appended with their normalised graph score scaled by ``graph_alpha``.
    """
    vector_normalised = _normalise_scores({h.note.id: h.score for h in vector_hits})
    graph_score_map: dict[object, float] = {}
    graph_notes: dict[object, object] = {}
    for hit in graph_hits:
        score = float(getattr(hit, "score", 0.0))
        note = getattr(hit, "note", None)
        if note is None:
            continue
        graph_score_map[note.id] = score
        graph_notes[note.id] = note
    graph_normalised = _normalise_scores(graph_score_map)

    blended: dict[object, float] = {}
    seen_notes: dict[object, object] = {h.note.id: h.note for h in vector_hits}
    for nid, vscore in vector_normalised.items():
        gscore = graph_normalised.get(nid, 0.0)
        blended[nid] = (1.0 - graph_alpha) * vscore + graph_alpha * gscore
    for nid, gscore in graph_normalised.items():
        if nid in blended:
            continue
        blended[nid] = graph_alpha * gscore
        seen_notes.setdefault(nid, graph_notes[nid])
    return [
        RetrievalHit(note=seen_notes[nid], score=score)  # type: ignore[arg-type]
        for nid, score in blended.items()
    ]


def _normalise_scores(scores: dict[object, float]) -> dict[object, float]:
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    if hi == lo:
        return {k: 0.0 for k in scores}
    span = hi - lo
    return {k: (v - lo) / span for k, v in scores.items()}
