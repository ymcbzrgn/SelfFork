"""L1 Recency-decay compaction (ADR-002 §4).

Generative-Agents 2023 formula adapted: each note's importance is
exponentially decayed by age and bumped by recent access. Pinned notes
are exempt.

The strategy does **not** evict notes; it only re-scores ``importance``
so downstream retrieval ranks fresh-or-pinned notes ahead of old-and-
unused ones. Eviction happens at L3 (clustering) or L4 (LLM summary).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from selffork_mind.compaction.base import (
    CompactionPlan,
    ImportanceUpdate,
)
from selffork_mind.memory.model import Note

__all__ = ["RecencyDecayCompactor"]


class RecencyDecayCompactor:
    """Re-scores ``importance`` based on age — no eviction at L1."""

    layer: Literal["recency"] = "recency"

    def __init__(
        self,
        *,
        half_life_seconds: float = 7 * 24 * 3600,
        floor: float = 0.05,
        ceiling: float = 10.0,
    ) -> None:
        if half_life_seconds <= 0:
            raise ValueError("half_life_seconds must be positive")
        if floor < 0 or ceiling <= floor:
            raise ValueError("floor and ceiling must satisfy 0 ≤ floor < ceiling")
        self._half_life = half_life_seconds
        self._floor = floor
        self._ceiling = ceiling

    async def plan(
        self,
        *,
        notes: Sequence[Note],
    ) -> CompactionPlan:
        if not notes:
            return CompactionPlan(layer=self.layer)
        now = datetime.now(UTC)
        updates: list[ImportanceUpdate] = []
        decayed = 0
        unchanged = 0
        for note in notes:
            if note.pinned:
                unchanged += 1
                continue
            age_seconds = max(0.0, (now - note.valid_from).total_seconds())
            decay = 0.5 ** (age_seconds / self._half_life)
            new_score = max(
                self._floor,
                min(self._ceiling, float(note.importance) * decay),
            )
            if abs(new_score - note.importance) < 1e-9:
                unchanged += 1
                continue
            updates.append(
                ImportanceUpdate(note_id=note.id, new_importance=new_score),
            )
            decayed += 1
        return CompactionPlan(
            layer=self.layer,
            importance_updates=tuple(updates),
            summary={
                "decayed": decayed,
                "unchanged": unchanged,
                "half_life_seconds": self._half_life,
            },
        )
