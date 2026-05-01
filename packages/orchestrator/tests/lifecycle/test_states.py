"""Unit tests for the session lifecycle state machine."""

from __future__ import annotations

import pytest

from selffork_orchestrator.lifecycle.states import (
    ALLOWED_TRANSITIONS,
    SessionState,
    is_legal_transition,
)


class TestEnumValues:
    @pytest.mark.parametrize(
        "state",
        [
            SessionState.IDLE,
            SessionState.PREPARING,
            SessionState.RUNNING,
            SessionState.VERIFYING,
            SessionState.COMPLETED,
            SessionState.FAILED,
            SessionState.TORN_DOWN,
        ],
    )
    def test_each_state_in_table(self, state: SessionState) -> None:
        assert state in ALLOWED_TRANSITIONS


class TestLegalTransitions:
    @pytest.mark.parametrize(
        ("from_state", "to_state"),
        [
            (SessionState.IDLE, SessionState.PREPARING),
            (SessionState.PREPARING, SessionState.RUNNING),
            (SessionState.PREPARING, SessionState.FAILED),
            (SessionState.RUNNING, SessionState.VERIFYING),
            (SessionState.RUNNING, SessionState.COMPLETED),
            (SessionState.RUNNING, SessionState.FAILED),
            (SessionState.VERIFYING, SessionState.COMPLETED),
            (SessionState.VERIFYING, SessionState.FAILED),
            (SessionState.COMPLETED, SessionState.TORN_DOWN),
            (SessionState.FAILED, SessionState.TORN_DOWN),
        ],
    )
    def test_legal(self, from_state: SessionState, to_state: SessionState) -> None:
        assert is_legal_transition(from_state, to_state)


class TestIllegalTransitions:
    @pytest.mark.parametrize(
        ("from_state", "to_state"),
        [
            (SessionState.IDLE, SessionState.RUNNING),
            (SessionState.IDLE, SessionState.COMPLETED),
            (SessionState.PREPARING, SessionState.COMPLETED),
            (SessionState.PREPARING, SessionState.VERIFYING),
            (SessionState.RUNNING, SessionState.IDLE),
            (SessionState.COMPLETED, SessionState.RUNNING),
            (SessionState.COMPLETED, SessionState.FAILED),
            (SessionState.FAILED, SessionState.COMPLETED),
            (SessionState.TORN_DOWN, SessionState.IDLE),
            (SessionState.TORN_DOWN, SessionState.PREPARING),
        ],
    )
    def test_illegal(self, from_state: SessionState, to_state: SessionState) -> None:
        assert not is_legal_transition(from_state, to_state)


class TestTerminal:
    def test_torn_down_has_no_legal_next(self) -> None:
        assert ALLOWED_TRANSITIONS[SessionState.TORN_DOWN] == frozenset()
