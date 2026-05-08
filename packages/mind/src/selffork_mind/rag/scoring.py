"""Pluggable scoring stack for the hybrid retriever.

Per ADR-002 §5 (Multi-strategy retrieval, Hindsight 20/20 fusion):

- :class:`Scorer` Protocol — single-stage scorer; given a query and a list
  of candidate notes, returns a per-note score map. Concrete impls:
    * :class:`SemanticScorer` — passes through the store's vector cosine.
    * :class:`BM25Scorer` — lexical, ``rank_bm25`` (BM25Okapi + tokeniser).
    * :class:`TagBoostScorer` — fixed-magnitude bump per matching ``(key,
      value)`` pair the operator asked for.

- :class:`ConvexFusionScorer` — combines a list of weighted scorers into
  one score-per-note via min-max normalisation + convex sum. Default
  weights are ``(semantic 0.55, bm25 0.35, tag 0.10)`` (mem0 multi-signal
  ratio, ``examples_crucial/mem0/mem0/memory/main.py:1343-1499``).

The scorers don't talk to the store — the retriever feeds them already-
fetched candidate notes plus the candidate-level vector cosine produced
by the store. This keeps each scorer pure-Python and trivially testable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from rank_bm25 import BM25Okapi

from selffork_mind.memory.model import Note

__all__ = [
    "BM25Scorer",
    "ConvexFusionScorer",
    "ScoredCandidate",
    "Scorer",
    "SemanticScorer",
    "TagBoostScorer",
    "WeightedScorer",
    "tokenize",
]


_TOKEN_RE = re.compile(r"[\w]+", flags=re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Lower-cased word-token split (unicode-aware).

    BM25 needs a tokeniser; we keep ours trivial — split on non-word
    characters, lower-case, drop empties. Multilingual (Turkish + English)
    works because :data:`_TOKEN_RE` uses unicode word matching.
    """
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """One scored note. ``score`` is the post-fusion final score."""

    note: Note
    score: float


class Scorer(Protocol):
    """One-stage scorer; returns ``{note_id: raw_score}`` for the candidates.

    Implementations are pure: no I/O, no store calls. The retriever owns
    the store handle and pre-fetches candidates.
    """

    name: str

    def score(
        self,
        *,
        query: str,
        query_embedding: tuple[float, ...] | None,
        candidates: Sequence[Note],
        per_note_vector_score: dict[UUID, float] | None = None,
        tag_pairs: tuple[tuple[str, str], ...] = (),
        tag_pairs_per_note: dict[UUID, set[tuple[str, str]]] | None = None,
    ) -> dict[UUID, float]: ...


# ── Concrete scorers ──────────────────────────────────────────────────────


class SemanticScorer:
    """Cosine similarity from the store's vector stage.

    The store has already cosine-scored every candidate (DuckDBMindStore
    `_score`); this scorer surfaces those scores into the fusion. Notes
    without a stored embedding fall back to the store's baseline value
    (already pre-set by the store).
    """

    name: str = "semantic"

    def score(
        self,
        *,
        query: str,
        query_embedding: tuple[float, ...] | None,
        candidates: Sequence[Note],
        per_note_vector_score: dict[UUID, float] | None = None,
        tag_pairs: tuple[tuple[str, str], ...] = (),
        tag_pairs_per_note: dict[UUID, set[tuple[str, str]]] | None = None,
    ) -> dict[UUID, float]:
        del query, query_embedding, tag_pairs, tag_pairs_per_note
        scores: dict[UUID, float] = {}
        if per_note_vector_score is None:
            return {n.id: 0.0 for n in candidates}
        for n in candidates:
            scores[n.id] = float(per_note_vector_score.get(n.id, 0.0))
        return scores


class BM25Scorer:
    """Lexical relevance via ``rank_bm25.BM25Okapi``.

    BM25 needs the full corpus for IDF; we pass ``candidates`` as the
    corpus per query (the candidate set is already filtered by tier +
    scope + tag-match in the retriever's first stage). Empty corpus or
    empty query returns all-zero scores.
    """

    name: str = "bm25"

    def score(
        self,
        *,
        query: str,
        query_embedding: tuple[float, ...] | None,
        candidates: Sequence[Note],
        per_note_vector_score: dict[UUID, float] | None = None,
        tag_pairs: tuple[tuple[str, str], ...] = (),
        tag_pairs_per_note: dict[UUID, set[tuple[str, str]]] | None = None,
    ) -> dict[UUID, float]:
        del query_embedding, per_note_vector_score, tag_pairs, tag_pairs_per_note
        if not candidates:
            return {}
        tokens_per_doc = [tokenize(n.content) for n in candidates]
        if all(not toks for toks in tokens_per_doc):
            return {n.id: 0.0 for n in candidates}
        # rank_bm25 raises on empty corpora. Replace any wholly empty
        # docs with a single sentinel token so BM25Okapi keeps working.
        sanitised = [toks if toks else ["__empty__"] for toks in tokens_per_doc]
        bm25 = BM25Okapi(sanitised)
        query_tokens = tokenize(query)
        if not query_tokens:
            return {n.id: 0.0 for n in candidates}
        raw_scores = bm25.get_scores(query_tokens)
        return {n.id: float(score) for n, score in zip(candidates, raw_scores, strict=True)}


class TagBoostScorer:
    """Adds a fixed-magnitude boost for every matching tag pair.

    The operator's ``tag_pairs`` (already the filter the retriever
    enforced) is what we boost on. Notes that carry MORE of the
    requested tags rank higher than those with one — this is a
    deliberate ranking signal (mem0 multi-signal pattern).
    """

    name: str = "tag_boost"

    def __init__(self, *, per_match_weight: float = 1.0) -> None:
        self._per_match = per_match_weight

    def score(
        self,
        *,
        query: str,
        query_embedding: tuple[float, ...] | None,
        candidates: Sequence[Note],
        per_note_vector_score: dict[UUID, float] | None = None,
        tag_pairs: tuple[tuple[str, str], ...] = (),
        tag_pairs_per_note: dict[UUID, set[tuple[str, str]]] | None = None,
    ) -> dict[UUID, float]:
        del query, query_embedding, per_note_vector_score
        if not tag_pairs or tag_pairs_per_note is None:
            return {n.id: 0.0 for n in candidates}
        wanted: set[tuple[str, str]] = set(tag_pairs)
        out: dict[UUID, float] = {}
        for note in candidates:
            attached = tag_pairs_per_note.get(note.id, set())
            matches = len(wanted & attached)
            out[note.id] = float(matches) * self._per_match
        return out


# ── Fusion ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WeightedScorer:
    scorer: Scorer
    weight: float


class ConvexFusionScorer:
    """Min-max normalise each component, then weighted-sum.

    Each component scorer is normalised to ``[0, 1]`` over the candidate
    set so weights have meaningful magnitudes. When a component returns
    constant scores (max == min), it contributes ``0`` to the fusion.
    Final score is the convex sum over all components.

    The default weights ``(semantic 0.55, bm25 0.35, tag_boost 0.10)``
    matches mem0's published multi-signal split. Override per-deployment
    by passing your own list to :meth:`build_default`.
    """

    name: str = "convex_fusion"

    def __init__(self, components: Sequence[WeightedScorer]) -> None:
        if not components:
            raise ValueError("ConvexFusionScorer needs at least one component")
        self._components = list(components)

    @classmethod
    def build_default(
        cls,
        *,
        semantic_weight: float = 0.55,
        bm25_weight: float = 0.35,
        tag_weight: float = 0.10,
        tag_per_match_weight: float = 1.0,
    ) -> ConvexFusionScorer:
        """The published mem0 weights, exposed for swapping."""
        return cls(
            [
                WeightedScorer(SemanticScorer(), semantic_weight),
                WeightedScorer(BM25Scorer(), bm25_weight),
                WeightedScorer(
                    TagBoostScorer(per_match_weight=tag_per_match_weight),
                    tag_weight,
                ),
            ],
        )

    def score(
        self,
        *,
        query: str,
        query_embedding: tuple[float, ...] | None,
        candidates: Sequence[Note],
        per_note_vector_score: dict[UUID, float] | None = None,
        tag_pairs: tuple[tuple[str, str], ...] = (),
        tag_pairs_per_note: dict[UUID, set[tuple[str, str]]] | None = None,
    ) -> dict[UUID, float]:
        if not candidates:
            return {}
        accumulator: dict[UUID, float] = {n.id: 0.0 for n in candidates}
        for component in self._components:
            raw = component.scorer.score(
                query=query,
                query_embedding=query_embedding,
                candidates=candidates,
                per_note_vector_score=per_note_vector_score,
                tag_pairs=tag_pairs,
                tag_pairs_per_note=tag_pairs_per_note,
            )
            normalised = _min_max(raw, candidates)
            for n in candidates:
                accumulator[n.id] += component.weight * normalised.get(n.id, 0.0)
        return accumulator


def _min_max(
    raw: dict[UUID, float],
    candidates: Iterable[Note],
) -> dict[UUID, float]:
    values = [raw.get(n.id, 0.0) for n in candidates]
    if not values:
        return {}
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return {n.id: 0.0 for n in candidates}
    span = hi - lo
    return {n.id: (raw.get(n.id, 0.0) - lo) / span for n in candidates}
