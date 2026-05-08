"""Pure-Python in-memory implementation of :class:`SemanticGraphStore`.

Reference backend used by the test suite + the production default when
``selffork-mind[graph-kuzu]`` is not installed. No persistence; the
store rebuilds itself from Episodic + Procedural notes via the
consolidation pipeline.

Concurrency: single-process, single-writer (no internal lock — Mind T3
operations sit behind the orchestrator's session loop, not user-facing).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from selffork_mind.graph.base import GraphTriple

__all__ = ["InMemoryGraphStore"]


class InMemoryGraphStore:
    """Reference :class:`SemanticGraphStore` impl — pure Python."""

    def __init__(self) -> None:
        # Identity key includes valid_from so superseding a fact (writing
        # a closed copy of the prior + a new live successor for the same
        # (s,p,o,src)) preserves the historical row instead of overwriting
        # it. Mirrors the Graphiti append-only model (ADR-002 §6).
        self._triples: dict[
            tuple[str, str, str, UUID, datetime],
            GraphTriple,
        ] = {}
        self._passage_phrases: dict[UUID, set[str]] = defaultdict(set)
        self._phrase_passages: dict[str, set[UUID]] = defaultdict(set)
        self._setup_done = False

    async def setup(self) -> None:
        self._setup_done = True

    async def teardown(self) -> None:
        self._setup_done = False

    # ── triples ──────────────────────────────────────────────────────────

    async def add_triple(self, triple: GraphTriple) -> None:
        key = (
            triple.subject,
            triple.predicate,
            triple.obj,
            triple.source_passage_id,
            triple.valid_from,
        )
        self._triples[key] = triple

    async def add_triples(self, triples: Sequence[GraphTriple]) -> None:
        for triple in triples:
            await self.add_triple(triple)

    async def supersede_triple(
        self,
        *,
        subject: str,
        predicate: str,
        object_: str,
        source_passage_id: UUID,
        at: datetime | None = None,
    ) -> bool:
        # Find the LIVE row (valid_until is None) for this (s,p,o,src).
        live_key: tuple[str, str, str, UUID, datetime] | None = None
        live_existing: GraphTriple | None = None
        for key, existing in self._triples.items():
            if (
                existing.subject == subject
                and existing.predicate == predicate
                and existing.obj == object_
                and existing.source_passage_id == source_passage_id
                and existing.valid_until is None
            ):
                live_key = key
                live_existing = existing
                break
        if live_key is None or live_existing is None:
            return False
        moment = at if at is not None else datetime.now(UTC)
        # Stamp the existing row's valid_until in place (the row stays
        # under its original key).
        self._triples[live_key] = GraphTriple(
            subject=live_existing.subject,
            predicate=live_existing.predicate,
            obj=live_existing.obj,
            source_passage_id=live_existing.source_passage_id,
            project_slug=live_existing.project_slug,
            confidence=live_existing.confidence,
            valid_from=live_existing.valid_from,
            valid_until=moment,
        )
        return True

    async def list_triples(
        self,
        *,
        project_slug: str | None = None,
        subject: str | None = None,
        predicate: str | None = None,
        object_: str | None = None,
        valid_at: datetime | None = None,
    ) -> list[GraphTriple]:
        moment = valid_at
        out: list[GraphTriple] = []
        for triple in self._triples.values():
            if project_slug is not None and triple.project_slug != project_slug:
                continue
            if subject is not None and triple.subject != subject:
                continue
            if predicate is not None and triple.predicate != predicate:
                continue
            if object_ is not None and triple.obj != object_:
                continue
            if moment is not None and not triple.is_currently_valid(at=moment):
                continue
            out.append(triple)
        # Deterministic ordering — by (subject, predicate, object).
        out.sort(key=lambda t: (t.subject, t.predicate, t.obj, str(t.source_passage_id)))
        return out

    # ── passage / phrase ─────────────────────────────────────────────────

    async def add_passage(self, *, passage_id: UUID, phrases: Sequence[str]) -> None:
        for phrase in phrases:
            self._passage_phrases[passage_id].add(phrase)
            self._phrase_passages[phrase].add(passage_id)

    async def list_phrases_for_passage(self, passage_id: UUID) -> list[str]:
        return sorted(self._passage_phrases.get(passage_id, set()))

    async def list_passages_for_phrase(self, phrase: str) -> list[UUID]:
        return sorted(
            self._phrase_passages.get(phrase, set()),
            key=lambda u: str(u),
        )

    async def list_phrase_neighbours(
        self,
        phrase: str,
        *,
        max_hops: int = 2,
    ) -> list[str]:
        """BFS from ``phrase`` through passage→phrase contains-edges."""
        if phrase not in self._phrase_passages:
            return []
        visited: set[str] = {phrase}
        frontier: set[str] = {phrase}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for cur in frontier:
                for passage_id in self._phrase_passages.get(cur, set()):
                    for neighbour in self._passage_phrases.get(passage_id, set()):
                        if neighbour not in visited:
                            next_frontier.add(neighbour)
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        visited.discard(phrase)
        return sorted(visited)
