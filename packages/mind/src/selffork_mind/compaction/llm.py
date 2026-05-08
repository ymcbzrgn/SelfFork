"""L4 LLM-summary compaction (ADR-002 §4, opt-in).

Calls a user-provided async ``llm_synth`` to summarise a candidate
window into a single Note (one summary per cluster), then supersedes the
clustered originals. **Always opt-in** — never the default. The CLI
gates this behind ``--strategy llm --apply`` because it spends real
tokens.

The summariser receives the cluster's notes and returns a single string;
the strategy wraps that string into a ``tier="reflection"`` /
``kind="reflection"`` Note (matching :class:`Reflector`'s output shape so
downstream retrievers see one consistent reflection family). Failures
silently fall through — no spurious supersessions on LLM error.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from selffork_mind.compaction.base import (
    CompactionPlan,
    NoteCluster,
)
from selffork_mind.compaction.cluster import MedoidClusterCompactor
from selffork_mind.memory.model import Note
from selffork_mind.store.base import MindStore

__all__ = ["LLMSummaryCompactor"]


LLMSummariser = Callable[[Sequence[Note]], Awaitable[str]]


class LLMSummaryCompactor:
    """L4 — LLM-driven cluster summarisation; opt-in only."""

    layer: Literal["cluster"] = "cluster"
    """Reuses the ``cluster`` layer label so apply_plan supersedes the
    non-representative members exactly as L3 would. The summary text is
    folded into the cluster's representative passage_id (see
    :meth:`plan` — we materialise a synthetic representative note in
    ``MindStore`` first).
    """

    def __init__(
        self,
        *,
        store: MindStore,
        clusterer: MedoidClusterCompactor | None = None,
        llm_summarise: LLMSummariser,
        importance: float = 7.5,
        project_slug: str | None = None,
    ) -> None:
        self._store = store
        self._clusterer = clusterer or MedoidClusterCompactor(
            store=store,
            distance_cutoff=0.45,
            min_cluster_size=2,
        )
        self._summarise = llm_summarise
        self._importance = importance
        self._project_slug = project_slug

    async def plan(
        self,
        *,
        notes: Sequence[Note],
    ) -> CompactionPlan:
        cluster_plan = await self._clusterer.plan(notes=notes)
        if not cluster_plan.clusters:
            return CompactionPlan(
                layer=self.layer,
                summary={
                    "reason": "no_clusters_for_summary",
                    **cluster_plan.summary,
                },
            )
        notes_by_id = {n.id: n for n in notes}
        new_clusters: list[NoteCluster] = []
        summaries_written: list[Note] = []
        for cluster in cluster_plan.clusters:
            members = [notes_by_id[mid] for mid in cluster.member_ids if mid in notes_by_id]
            if not members:
                continue
            try:
                summary_text = await self._summarise(members)
            except Exception:  # noqa: S112 — LLM failure → silent skip (no token waste)
                continue
            if not summary_text.strip():
                continue
            summary_note = Note(
                tier="reflection",
                kind="reflection",
                content=json.dumps(
                    {
                        "type": "llm_summary",
                        "summary": summary_text,
                        "member_ids": [str(m.id) for m in members],
                    },
                    ensure_ascii=False,
                ),
                intent=f"summary:{members[0].id}",
                project_slug=self._project_slug
                if self._project_slug is not None
                else members[0].project_slug,
                source_pointer=f"summary:{members[0].id}",
                importance=self._importance,
                valid_from=datetime.now(UTC),
            )
            stored = await self._store.upsert_note(summary_note)
            summaries_written.append(stored)
            new_clusters.append(
                NoteCluster(
                    representative_id=stored.id,
                    member_ids=tuple(_dedup_keep(stored.id, cluster.member_ids)),
                ),
            )
        return CompactionPlan(
            layer=self.layer,
            clusters=tuple(new_clusters),
            summary={
                "summaries_written": len(summaries_written),
                "candidates": cluster_plan.summary.get("candidates", 0),
            },
        )


def _dedup_keep(rep: UUID, ids: Sequence[UUID]) -> list[UUID]:
    out: list[UUID] = [rep]
    seen = {rep}
    for mid in ids:
        if mid in seen:
            continue
        seen.add(mid)
        out.append(mid)
    return out
