"""L2 Importance distillation (ADR-002 §4).

Pattern-matching extraction of "decision sentinels" — notes whose
``intent`` looks decision-like (contains tokens like "decide", "lock",
"choose", "pick", "select", "default"). Their importance is bumped so
downstream retrieval surfaces them; non-decision-like notes whose
importance has already decayed below ``evict_threshold`` are flagged for
supersession (they survive in audit JSONL via T6 Recall, just not in
the active store).

This is **not** the Episodic→Procedural transfer (that's
:class:`~selffork_mind.memory.tiers.procedural.ProceduralDistiller`).
This is the importance-rebalancing step that runs **before** Procedural
distillation, so the distiller sees a corpus where signal is up and
noise is down.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from selffork_mind.compaction.base import (
    CompactionPlan,
    ImportanceUpdate,
)
from selffork_mind.memory.model import Note

__all__ = ["ImportanceDistiller"]


_DECISION_TOKENS: frozenset[str] = frozenset(
    {
        # English
        "decide",
        "decision",
        "lock",
        "locked",
        "choose",
        "chosen",
        "pick",
        "picked",
        "select",
        "selected",
        "default",
        "approve",
        "approved",
        "ratify",
        "ratified",
        # Turkish (operator's primary language; Pillar 3 SSOT
        # `docs/Yamac_Jr_Nano_Kararlar.md` is Turkish).
        "karar",
        "kararlı",
        "kilit",
        "kilitli",
        "kilitlendi",
        "seç",
        "seçtik",
        "seçildi",
        "seçim",
        "onay",
        "onaylandı",
        "onayladık",
        "kabul",
        "tercih",
        "tercihim",
    },
)


class ImportanceDistiller:
    """L2 — bump decision-like notes, flag low-importance noise."""

    layer: Literal["distill"] = "distill"

    def __init__(
        self,
        *,
        decision_bump: float = 1.5,
        ceiling: float = 10.0,
        evict_threshold: float = 0.1,
    ) -> None:
        if decision_bump <= 1.0:
            raise ValueError("decision_bump must be > 1.0 to actually bump")
        if ceiling <= 0 or evict_threshold < 0:
            raise ValueError("ceiling > 0 and evict_threshold ≥ 0 required")
        self._bump = decision_bump
        self._ceiling = ceiling
        self._evict = evict_threshold

    async def plan(
        self,
        *,
        notes: Sequence[Note],
    ) -> CompactionPlan:
        if not notes:
            return CompactionPlan(layer=self.layer)
        updates: list[ImportanceUpdate] = []
        evictions: list[Note] = []
        bumped = 0
        for note in notes:
            if note.pinned:
                continue
            looks_like_decision = (
                note.kind == "decision"
                or _has_decision_token(note.intent)
                or _has_decision_token(note.content)
            )
            if looks_like_decision:
                new_score = min(
                    self._ceiling,
                    float(note.importance) * self._bump,
                )
                if abs(new_score - note.importance) >= 1e-9:
                    updates.append(
                        ImportanceUpdate(note_id=note.id, new_importance=new_score),
                    )
                    bumped += 1
                continue
            if float(note.importance) <= self._evict and note.tier in {"episodic", "working"}:
                evictions.append(note)
        return CompactionPlan(
            layer=self.layer,
            importance_updates=tuple(updates),
            supersede_ids=tuple(n.id for n in evictions),
            summary={
                "decisions_bumped": bumped,
                "evicted_below_threshold": len(evictions),
                "evict_threshold": self._evict,
            },
        )


def _has_decision_token(text: str) -> bool:
    if not text:
        return False
    tokens = {
        token for raw in text.lower().split() if (token := "".join(c for c in raw if c.isalnum()))
    }
    return bool(tokens & _DECISION_TOKENS)
