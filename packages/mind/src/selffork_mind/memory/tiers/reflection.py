"""T5 Reflection — generative-agents reflection-of-reflection cascade.

Per ADR-002 §1, §11: T5 holds "higher-level insights" — distilled
'lessons learned' from clusters of Episodic / Procedural notes. Order 5
ships **deterministic** reflection (cluster summary + decision-theme
roll-up); LLM-driven reflection lands as an opt-in follow-on inside the
same :class:`Reflector` (the ``llm_synth`` parameter).

Anthropic Auto Dream four-phase pipeline (2026-05-06 research preview):

1. **Orientation** — what changed since the last reflection?
2. **Gather Signal** — pull recent Episodic + Procedural in scope.
3. **Consolidation** — cluster the gathered notes (deterministic medoid
   clustering from Order 3) and emit one Reflection note per cluster.
4. **Prune & Index** — superseded prior reflections that are subsumed by
   the new cluster's representative.

The reflection notes carry ``tier="reflection"``, ``kind="reflection"``,
high importance (default 7.0 — between Procedural patterns and pinned
T1 Working blocks), and a JSON body with the cluster's representative
note id and the member ids the lesson was distilled from.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from selffork_mind.compaction import MedoidClusterCompactor
from selffork_mind.memory.model import Note
from selffork_mind.memory.tags import Tag
from selffork_mind.store.base import (
    MindStore,
    RetrieveConfig,
    StoreScope,
)

__all__ = [
    "ReflectionReport",
    "Reflector",
]


LLMSynth = Callable[[Sequence[Note]], Awaitable[str]]
"""Optional LLM synthesiser. Receives cluster members; returns body.

When provided, the reflection's body is the LLM's synthesised lesson
text instead of the deterministic JSON summary. Reflector gates this
behind ``--strategy llm`` so default (sleep-cycle) reflection stays
deterministic.
"""


@dataclass(frozen=True, slots=True)
class ReflectionReport:
    """Summary of a reflection cycle."""

    candidates_examined: int
    clusters_built: int
    reflections_written: int
    pruned: int

    def to_payload(self) -> dict[str, int]:
        return {
            "candidates_examined": self.candidates_examined,
            "clusters_built": self.clusters_built,
            "reflections_written": self.reflections_written,
            "pruned": self.pruned,
        }


class Reflector:
    """Anthropic Auto Dream four-phase reflection cycle (deterministic-first)."""

    def __init__(
        self,
        *,
        store: MindStore,
        clusterer: MedoidClusterCompactor | None = None,
        llm_synth: LLMSynth | None = None,
        max_window: int = 200,
        importance_floor: float = 7.0,
    ) -> None:
        self._store = store
        self._clusterer = clusterer or MedoidClusterCompactor(
            store=store,
            distance_cutoff=0.45,
            min_cluster_size=2,
        )
        self._llm_synth = llm_synth
        self._max_window = max_window
        self._importance = importance_floor

    async def reflect(
        self,
        *,
        project_slug: str | None,
        since: datetime | None = None,
    ) -> ReflectionReport:
        """Run one reflection cycle."""
        # Phase 1 — Orientation: what window are we reflecting over?
        orientation_anchor = since or _default_orientation_anchor()
        # Phase 2 — Gather Signal: Episodic + Procedural in scope.
        candidates = await self._gather(project_slug=project_slug)
        if not candidates:
            return ReflectionReport(
                candidates_examined=0,
                clusters_built=0,
                reflections_written=0,
                pruned=0,
            )
        # Phase 3 — Consolidation: cluster the candidates.
        plan = await self._clusterer.plan(notes=candidates)
        clusters_built = len(plan.clusters)
        if clusters_built == 0:
            return ReflectionReport(
                candidates_examined=len(candidates),
                clusters_built=0,
                reflections_written=0,
                pruned=0,
            )
        candidates_by_id = {n.id: n for n in candidates}
        new_reflections: list[Note] = []
        for cluster in plan.clusters:
            members = [
                candidates_by_id[mid] for mid in cluster.member_ids if mid in candidates_by_id
            ]
            if not members:
                continue
            body = await self._render_body(members=members)
            note = Note(
                tier="reflection",
                kind="reflection",
                content=body,
                intent=f"reflection:{cluster.representative_id}",
                project_slug=project_slug,
                source_pointer=f"reflection:{cluster.representative_id}",
                importance=self._importance,
            )
            new_reflections.append(note)
        if new_reflections:
            stored = await self._store.upsert_notes(new_reflections)
            tags: list[Tag] = []
            for note in stored:
                if note.project_slug is not None:
                    tags.append(
                        Tag.now(note_id=note.id, key="project", value=note.project_slug),
                    )
                tags.append(Tag.now(note_id=note.id, key="kind", value="reflection"))
                tags.append(
                    Tag.now(note_id=note.id, key="phase", value="auto_dream"),
                )
            if tags:
                await self._store.attach_tags(tags)

        # Phase 4 — Prune & Index: supersede reflections that pre-date this
        # cycle's anchor and aren't kept by the new representatives.
        pruned = await self._prune(
            project_slug=project_slug,
            anchor=orientation_anchor,
            keep_intents={n.intent for n in new_reflections},
        )
        return ReflectionReport(
            candidates_examined=len(candidates),
            clusters_built=clusters_built,
            reflections_written=len(new_reflections),
            pruned=pruned,
        )

    async def _gather(self, *, project_slug: str | None) -> list[Note]:
        config = RetrieveConfig(
            tiers=("episodic", "procedural"),
            scope=StoreScope(project_slug=project_slug),
            top_k=self._max_window,
            rerank_overfetch=1,
        )
        hits = await self._store.retrieve(config)
        return [h.note for h in hits]

    async def _render_body(self, *, members: Sequence[Note]) -> str:
        if self._llm_synth is not None:
            try:
                synthesised = await self._llm_synth(members)
            except Exception:
                synthesised = ""
            # Empty / whitespace-only synthesis falls back to the
            # deterministic body (matches LLMSummaryCompactor's contract;
            # avoids a high-importance reflection note with no content).
            if synthesised and synthesised.strip():
                return synthesised
        rep = members[0]
        snippets = [_truncate(n.content, 280) for n in members[:5]]
        payload = {
            "type": "deterministic_reflection",
            "representative_id": str(rep.id),
            "member_ids": [str(n.id) for n in members],
            "intents": [n.intent for n in members if n.intent],
            "snippet_count": len(snippets),
            "snippets": snippets,
            "rendered_at": datetime.now(UTC).isoformat(),
        }
        return json.dumps(payload, ensure_ascii=False)

    async def _prune(
        self,
        *,
        project_slug: str | None,
        anchor: datetime,
        keep_intents: set[str],
    ) -> int:
        config = RetrieveConfig(
            tiers=("reflection",),
            scope=StoreScope(project_slug=project_slug),
            top_k=500,
            rerank_overfetch=1,
        )
        hits = await self._store.retrieve(config)
        pruned = 0
        for hit in hits:
            note = hit.note
            if note.valid_from >= anchor:
                continue
            if note.intent in keep_intents:
                continue
            result = await self._store.supersede(note.id)
            if result is not None:
                pruned += 1
        return pruned


# ── module helpers ────────────────────────────────────────────────────────


def _default_orientation_anchor() -> datetime:
    return datetime.now(UTC)


def _truncate(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    return text[: n - 1].rstrip() + "…"
