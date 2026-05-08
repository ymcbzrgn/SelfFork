"""Three-pillar bridge — Mind → Reflex training corpus.

Per ADR-002 §"Three-pillar integration" (McClelland 1995 CLS):
Hippocampus ↔ Mind (T2 Episodic, fast write) ⇒ Sleep replay ↔ T4
Procedural distillation ⇒ Neocortex ↔ Reflex (slow adapter).

Order 6 ships:

- :class:`ReflexCorpusExporter` — walks T4 Procedural notes, applies
  Bjork desirable difficulties (spacing + interleaving + retrieval
  practice) and SM-2 E-Factor (operator correction frequency), emits a
  fine-tune-ready JSONL corpus.
- :class:`SM2Scheduler` — pure-Python SM-2 spaced repetition scheduler.
- :func:`shuffle_interleaved` — deterministic interleaving (Bjork
  desirable difficulty: avoid same-topic clustering in training data).

The corpus shape uses the standard ``{"messages": [...], "metadata":
{...}}`` JSONL format that the future Reflex training pipeline (M7,
``packages/reflex/`` is a skeleton today) will consume. The exporter
is **deterministic** — same Mind state + same config = same corpus.
"""

from __future__ import annotations

from selffork_mind.bridge.exporter import (
    ExportConfig,
    ExportReport,
    ReflexCorpusExporter,
    TrainingItem,
)
from selffork_mind.bridge.interleave import shuffle_interleaved
from selffork_mind.bridge.sm2 import (
    SM2Card,
    SM2Scheduler,
    sm2_e_factor,
    sm2_next_review,
)

__all__ = [
    "ExportConfig",
    "ExportReport",
    "ReflexCorpusExporter",
    "SM2Card",
    "SM2Scheduler",
    "TrainingItem",
    "shuffle_interleaved",
    "sm2_e_factor",
    "sm2_next_review",
]
