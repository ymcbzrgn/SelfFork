"""Session lifecycle — state machine and orchestration.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §6.
"""

from __future__ import annotations

from selffork_orchestrator.lifecycle.session import Session
from selffork_orchestrator.lifecycle.states import (
    ALLOWED_TRANSITIONS,
    SessionState,
    is_legal_transition,
)

__all__ = ["ALLOWED_TRANSITIONS", "Session", "SessionState", "is_legal_transition"]
