"""High-level GraphRetriever — HippoRAG 2 PPR over the semantic graph.

Per ADR-002 §5: graph routing for multi-hop / temporal / causal queries.

Pipeline:
1. Extract seed phrases from the operator's query (deterministic
   tokeniser; same one consolidation uses, so seeds align with stored
   phrases).
2. Build the (phrase ↔ passage) bipartite view by walking the graph
   store's contains-edges.
3. Run :func:`personalized_pagerank` to score every passage reachable
   from the seeds.
4. Fetch the corresponding :class:`Note` rows from the canonical
   :class:`MindStore` and return them as :class:`GraphHit` rows.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from selffork_mind.graph.base import SemanticGraphStore
from selffork_mind.graph.consolidation import extract_phrases
from selffork_mind.graph.ppr import personalized_pagerank
from selffork_mind.memory.model import Note
from selffork_mind.store.base import MindStore

__all__ = ["GraphHit", "GraphRetriever"]


@dataclass(frozen=True, slots=True)
class GraphHit:
    """One scored passage from a graph recall."""

    note: Note
    score: float


class GraphRetriever:
    """HippoRAG 2 PPR retriever over the semantic graph."""

    def __init__(
        self,
        *,
        store: MindStore,
        graph: SemanticGraphStore,
        alpha: float = 0.5,
        iterations: int = 30,
        max_seed_phrases: int = 8,
    ) -> None:
        self._store = store
        self._graph = graph
        self._alpha = alpha
        self._iterations = iterations
        self._max_seed = max_seed_phrases

    async def recall(
        self,
        *,
        query: str,
        top_k: int = 10,
        threshold: float = 0.0,
    ) -> list[GraphHit]:
        """Run a graph recall.

        Returns up to ``top_k`` passages scored by PPR. ``threshold``
        cuts low-mass walks; default ``0.0`` keeps everything reachable.
        """
        if not query.strip():
            return []
        seeds = extract_phrases(query, max_phrases=self._max_seed)
        if not seeds:
            return []

        phrase_to_passages, passage_to_phrases = await self._build_bipartite(seeds)
        if not phrase_to_passages:
            return []

        scores = personalized_pagerank(
            seeds=seeds,
            phrase_to_passages=phrase_to_passages,
            passage_to_phrases=passage_to_phrases,
            alpha=self._alpha,
            iterations=self._iterations,
        )
        if not scores:
            return []

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        head = [(pid, s) for pid, s in ranked if s >= threshold][:top_k]
        if not head:
            return []
        notes = await self._store.get_notes([pid for pid, _ in head])
        by_id = {n.id: n for n in notes}
        out: list[GraphHit] = []
        for pid, score in head:
            note = by_id.get(pid)
            if note is None:
                continue
            out.append(GraphHit(note=note, score=float(score)))
        return out

    async def _build_bipartite(
        self,
        seeds: Sequence[str],
    ) -> tuple[dict[str, list[UUID]], dict[UUID, list[str]]]:
        """Walk the contains-edges out from the seeds for ≤2 hops.

        Two hops keeps the candidate set bounded while still picking up
        passages reachable via a shared phrase (HippoRAG 2's typical
        recall radius).
        """
        phrase_to_passages: dict[str, list[UUID]] = {}
        passage_to_phrases: dict[UUID, set[str]] = defaultdict(set)

        seen_phrases: set[str] = set(seeds)
        frontier: set[str] = set(seeds)
        for hop in range(3):  # seed (hop 0) + 2 outward hops
            del hop
            next_frontier: set[str] = set()
            for phrase in frontier:
                passages = await self._graph.list_passages_for_phrase(phrase)
                if not passages:
                    continue
                phrase_to_passages.setdefault(phrase, []).extend(
                    pid for pid in passages if pid not in phrase_to_passages.get(phrase, [])
                )
                for pid in passages:
                    if pid in passage_to_phrases:
                        continue
                    pid_phrases = await self._graph.list_phrases_for_passage(pid)
                    passage_to_phrases[pid] = set(pid_phrases)
                    for p in pid_phrases:
                        if p not in seen_phrases:
                            seen_phrases.add(p)
                            next_frontier.add(p)
            frontier = next_frontier
            if not frontier:
                break
        # Also ensure phrase_to_passages includes the indirect phrases so
        # PPR can route through them.
        for _pid, ps in passage_to_phrases.items():
            for p in ps:
                if p not in phrase_to_passages:
                    # Look up the canonical passages for that phrase too.
                    extra = await self._graph.list_passages_for_phrase(p)
                    phrase_to_passages[p] = list(dict.fromkeys(extra))
        passage_lists: dict[UUID, list[str]] = {
            pid: sorted(ps) for pid, ps in passage_to_phrases.items()
        }
        return phrase_to_passages, passage_lists
