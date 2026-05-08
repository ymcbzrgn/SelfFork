"""Compaction strategy primitives.

Per ADR-002 §4: four-layer "forgetting curve" (L1 Recency-decay, L2
Importance distillation, L3 Semantic clustering, L4 LLM-summary). Order
3 ships L1-L3 (deterministic). L4 is a separate Order 5 strategy.

Every strategy is a :class:`CompactionStrategy` Protocol implementer:
takes a list of candidate notes (the retriever's pre-fetched window),
returns a :class:`CompactionPlan` describing what to keep / supersede /
cluster. The caller decides whether to apply (live store mutation) or
treat the plan as a dry-run (audit it, return it to the operator).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from selffork_mind.memory.model import Note

__all__ = [
    "CompactionPlan",
    "CompactionStrategy",
    "ImportanceUpdate",
    "NoteCluster",
]


@dataclass(frozen=True, slots=True)
class ImportanceUpdate:
    """One note's importance score after the strategy ran."""

    note_id: UUID
    new_importance: float


@dataclass(frozen=True, slots=True)
class NoteCluster:
    """A k-means / medoid cluster — only the representative survives.

    ``representative_id`` is the medoid. ``member_ids`` includes every
    note in the cluster, including the representative. The strategy's
    caller may supersede every non-representative member when applying.
    """

    representative_id: UUID
    member_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class CompactionPlan:
    """Output of one compaction strategy.

    ``layer`` identifies the source strategy so audit logs can describe
    what fired; the orchestrator's ``selffork mind compact`` CLI uses
    this for the dry-run summary.
    """

    layer: Literal["recency", "distill", "cluster"]
    importance_updates: tuple[ImportanceUpdate, ...] = ()
    supersede_ids: tuple[UUID, ...] = ()
    clusters: tuple[NoteCluster, ...] = ()
    summary: dict[str, object] = field(default_factory=dict)
    """Free-form per-strategy stats (e.g. ``"clusters_built": 3``)."""

    def is_empty(self) -> bool:
        return not self.importance_updates and not self.supersede_ids and not self.clusters


@runtime_checkable
class CompactionStrategy(Protocol):
    """One compaction layer.

    Strategies are pure: they read input notes, return a plan. The
    caller (``selffork mind compact``, the orchestrator's memory replay
    job) writes the plan back to the store.
    """

    layer: Literal["recency", "distill", "cluster"]

    async def plan(
        self,
        *,
        notes: Sequence[Note],
    ) -> CompactionPlan: ...
