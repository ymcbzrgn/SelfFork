"""Reflection orchestration (ADR-009 §4 Auto Dream tetikleyici).

Wraps the deterministic four-phase :class:`~selffork_mind.memory.tiers.reflection.Reflector`
(Order 5) with the threshold gate (24h elapsed + ≥5 sessions accumulated +
not rate-limited + idle) and GLOBAL pool routing.
"""

from __future__ import annotations

from selffork_mind.reflection.auto_dream import (
    AutoDreamCheckpoint,
    AutoDreamConfig,
    AutoDreamGate,
    AutoDreamReport,
    AutoDreamRunner,
    GateDecision,
    load_dream_checkpoint,
    save_dream_checkpoint,
)

__all__ = [
    "AutoDreamCheckpoint",
    "AutoDreamConfig",
    "AutoDreamGate",
    "AutoDreamReport",
    "AutoDreamRunner",
    "GateDecision",
    "load_dream_checkpoint",
    "save_dream_checkpoint",
]
