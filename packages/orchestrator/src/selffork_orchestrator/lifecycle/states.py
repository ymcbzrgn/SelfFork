"""Session lifecycle state machine — states + legal transition table.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §6 for the diagram and rationale.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["ALLOWED_TRANSITIONS", "SessionState", "is_legal_transition"]


class SessionState(StrEnum):
    """States of one ``selffork run`` invocation."""

    IDLE = "idle"
    PREPARING = "preparing"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    TORN_DOWN = "torn_down"


# Legal next-states from a given current state.
#
# Hand-written from the ADR §6 diagram. ``IDLE → PREPARING`` is the only
# entry transition. ``RUNNING`` may go straight to ``COMPLETED`` when
# ``LifecycleConfig.skip_verify`` is true. Both ``COMPLETED`` and ``FAILED``
# always end at ``TORN_DOWN`` via the orchestrator's ``finally`` block.
ALLOWED_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.IDLE: frozenset({SessionState.PREPARING}),
    SessionState.PREPARING: frozenset(
        {
            SessionState.RUNNING,
            SessionState.FAILED,
        }
    ),
    SessionState.RUNNING: frozenset(
        {
            SessionState.VERIFYING,
            SessionState.COMPLETED,  # skip_verify=True path
            SessionState.FAILED,
        }
    ),
    SessionState.VERIFYING: frozenset(
        {
            SessionState.COMPLETED,
            SessionState.FAILED,
        }
    ),
    SessionState.COMPLETED: frozenset({SessionState.TORN_DOWN}),
    SessionState.FAILED: frozenset({SessionState.TORN_DOWN}),
    SessionState.TORN_DOWN: frozenset(),  # terminal
}


def is_legal_transition(from_state: SessionState, to_state: SessionState) -> bool:
    """Return ``True`` if ``from_state → to_state`` is in :data:`ALLOWED_TRANSITIONS`."""
    return to_state in ALLOWED_TRANSITIONS.get(from_state, frozenset())
