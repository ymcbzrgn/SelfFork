"""Mind compaction layers (ADR-002 §4).

Order 3 ships L1-L3 (deterministic). L4 (LLM-summary, opt-in) lands
Order 5 alongside the reflection cycle.

Public surface:

- :class:`CompactionStrategy` Protocol + :class:`CompactionPlan` shape.
- :class:`RecencyDecayCompactor` — L1.
- :class:`ImportanceDistiller` — L2.
- :class:`MedoidClusterCompactor` — L3.
- :func:`apply_plan` — write a plan back to the store.
"""

from __future__ import annotations

from collections.abc import Sequence

from selffork_mind.compaction.base import (
    CompactionPlan,
    CompactionStrategy,
    ImportanceUpdate,
    NoteCluster,
)
from selffork_mind.compaction.cluster import MedoidClusterCompactor
from selffork_mind.compaction.distill import ImportanceDistiller
from selffork_mind.compaction.llm import LLMSummaryCompactor
from selffork_mind.compaction.recency import RecencyDecayCompactor
from selffork_mind.memory.model import Note
from selffork_mind.store.base import MindStore

__all__ = [
    "CompactionPlan",
    "CompactionStrategy",
    "ImportanceDistiller",
    "ImportanceUpdate",
    "LLMSummaryCompactor",
    "MedoidClusterCompactor",
    "NoteCluster",
    "RecencyDecayCompactor",
    "apply_plan",
]


async def apply_plan(
    plan: CompactionPlan,
    *,
    store: MindStore,
    notes: Sequence[Note] | None = None,
) -> dict[str, int]:
    """Mutate the store according to ``plan``.

    Returns counts of writes made — useful for ``mind.compact.run``
    audit payload. Pass ``notes`` (the same window the plan was built
    from) when applying importance updates so we can rewrite the full
    note row; otherwise we look each note up by id.
    """
    notes_by_id: dict[object, Note] = {}
    if notes is not None:
        notes_by_id = {n.id: n for n in notes}

    importance_count = 0
    for update in plan.importance_updates:
        note = notes_by_id.get(update.note_id)
        if note is None:
            note = await store.get_note(update.note_id)
        if note is None:
            continue
        await store.upsert_note(
            note.model_copy(update={"importance": update.new_importance}),
        )
        importance_count += 1

    supersede_count = 0
    for note_id in plan.supersede_ids:
        result = await store.supersede(note_id)
        if result is not None:
            supersede_count += 1

    cluster_supersede_count = 0
    for cluster in plan.clusters:
        for member_id in cluster.member_ids:
            if member_id == cluster.representative_id:
                continue
            result = await store.supersede(member_id)
            if result is not None:
                cluster_supersede_count += 1

    return {
        "importance_updates": importance_count,
        "supersede": supersede_count,
        "cluster_supersede": cluster_supersede_count,
        "clusters_applied": len(plan.clusters),
    }
