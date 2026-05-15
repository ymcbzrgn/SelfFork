"""Unit tests for the M-1 WebSocket protocol primitives — Order 2.

The HTTP-side integration of these primitives is covered by
``test_server.py::TestWebSocketStream``. This module owns the unit
tests so a regression in :mod:`ws_protocol` itself surfaces with a
focused failure (no FastAPI/TestClient noise).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from selffork_orchestrator.dashboard.ws_protocol import (
    DEFAULT_REPLAY_BUFFER_SIZE,
    HEARTBEAT_INTERVAL_SECONDS,
    WS_EVENT_TYPES,
    BoundedReplayBuffer,
    HeartbeatTask,
    WsEnvelope,
    build_audit_envelope,
    build_gap_envelope,
    next_seq,
    parse_last_seq,
    replay_or_gap,
)


def _make_audit(seq: int, *, category: str = "session.state") -> WsEnvelope:
    return build_audit_envelope(
        seq=seq,
        payload={"category": category, "to": "preparing"},
        session_id="sess",
    )


# ── WsEnvelope schema ─────────────────────────────────────────────────────────


class TestWsEnvelope:
    def test_minimal_envelope_round_trips(self) -> None:
        env = WsEnvelope(
            seq=1,
            event_type="audit",
            payload={"category": "session.state"},
            ts=datetime(2026, 5, 9, 18, 0, 0, tzinfo=UTC),
        )
        wire = env.model_dump_json()
        round_tripped = WsEnvelope.model_validate_json(wire)
        assert round_tripped == env

    def test_seq_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError):
            WsEnvelope(
                seq=-1,
                event_type="audit",
                payload={},
                ts=datetime.now(UTC),
            )

    def test_unknown_event_type_rejected(self) -> None:
        with pytest.raises(ValueError):
            WsEnvelope(
                seq=1,
                event_type="not-a-real-type",  # type: ignore[arg-type]
                payload={},
                ts=datetime.now(UTC),
            )

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValueError):
            WsEnvelope.model_validate(
                {
                    "seq": 1,
                    "event_type": "audit",
                    "payload": {},
                    "ts": "2026-05-09T18:00:00Z",
                    "what_is_this": True,
                },
            )

    def test_event_type_constants_match_literal(self) -> None:
        # The Literal in the model and the public tuple must agree —
        # tests / TS mirror generators iterate the tuple.
        for et in WS_EVENT_TYPES:
            WsEnvelope(seq=0, event_type=et, payload={}, ts=datetime.now(UTC))


# ── next_seq ──────────────────────────────────────────────────────────────────


class TestNextSeq:
    def test_starts_at_one(self) -> None:
        counter = [0]
        assert next_seq(counter) == 1

    def test_monotonic(self) -> None:
        counter = [0]
        seqs = [next_seq(counter) for _ in range(5)]
        assert seqs == [1, 2, 3, 4, 5]


# ── BoundedReplayBuffer ───────────────────────────────────────────────────────


class TestBoundedReplayBuffer:
    def test_default_maxlen_is_200(self) -> None:
        assert BoundedReplayBuffer().maxlen == DEFAULT_REPLAY_BUFFER_SIZE

    def test_zero_maxlen_rejected(self) -> None:
        with pytest.raises(ValueError):
            BoundedReplayBuffer(maxlen=0)

    def test_append_and_replay_strictly_after_last_seq(self) -> None:
        buf = BoundedReplayBuffer(maxlen=10)
        for i in range(1, 6):
            buf.append(_make_audit(i))
        replayed = list(buf.replay_from(2))
        assert [e.seq for e in replayed] == [3, 4, 5]

    def test_replay_when_caught_up_yields_nothing(self) -> None:
        buf = BoundedReplayBuffer(maxlen=10)
        for i in range(1, 6):
            buf.append(_make_audit(i))
        assert list(buf.replay_from(5)) == []
        assert list(buf.replay_from(99)) == []

    def test_overflow_drops_oldest(self) -> None:
        buf = BoundedReplayBuffer(maxlen=3)
        for i in range(1, 6):
            buf.append(_make_audit(i))
        snap = buf.snapshot()
        assert [e.seq for e in snap] == [3, 4, 5]
        assert buf.oldest_seq == 3
        assert buf.newest_seq == 5

    def test_has_gap_when_client_falls_behind(self) -> None:
        buf = BoundedReplayBuffer(maxlen=3)
        # Buffer holds seq 3..5; client at seq 1 missed seq 2.
        for i in range(1, 6):
            buf.append(_make_audit(i))
        assert buf.has_gap_for(1) is True
        assert buf.has_gap_for(2) is False  # 2+1 == oldest
        assert buf.has_gap_for(3) is False  # within window
        assert buf.has_gap_for(5) is False  # caught up

    def test_no_gap_when_buffer_empty(self) -> None:
        buf = BoundedReplayBuffer()
        assert buf.has_gap_for(0) is False
        assert buf.has_gap_for(99) is False


# ── parse_last_seq ────────────────────────────────────────────────────────────


class TestParseLastSeq:
    def test_none_is_zero(self) -> None:
        assert parse_last_seq(None) == 0

    def test_int_passthrough(self) -> None:
        assert parse_last_seq(42) == 42

    def test_str_int_parsed(self) -> None:
        assert parse_last_seq("17") == 17

    def test_negative_clamped_to_zero(self) -> None:
        assert parse_last_seq("-5") == 0
        assert parse_last_seq(-3) == 0

    def test_garbage_clamped_to_zero(self) -> None:
        assert parse_last_seq("not-a-number") == 0
        assert parse_last_seq("") == 0


# ── replay_or_gap ─────────────────────────────────────────────────────────────


class TestReplayOrGap:
    def test_empty_buffer_yields_nothing(self) -> None:
        buf = BoundedReplayBuffer()
        seq = [0]
        out = list(replay_or_gap(buf, last_seq=0, seq_counter=seq))
        assert out == []

    def test_caught_up_client_gets_nothing(self) -> None:
        buf = BoundedReplayBuffer(maxlen=3)
        for i in range(1, 4):
            buf.append(_make_audit(i))
        seq = [3]  # we've already minted up to 3
        out = list(replay_or_gap(buf, last_seq=3, seq_counter=seq))
        assert out == []

    def test_replay_only_when_in_window(self) -> None:
        buf = BoundedReplayBuffer(maxlen=10)
        for i in range(1, 6):
            buf.append(_make_audit(i))
        seq = [5]
        out = list(replay_or_gap(buf, last_seq=2, seq_counter=seq))
        assert [e.seq for e in out] == [3, 4, 5]
        assert all(e.event_type == "audit" for e in out)

    def test_gap_emitted_when_buffer_overflowed(self) -> None:
        # Buffer has seq 3..5; client missed seq 1..2.
        buf = BoundedReplayBuffer(maxlen=3)
        for i in range(1, 6):
            buf.append(_make_audit(i))
        seq = [5]
        out = list(replay_or_gap(buf, last_seq=1, seq_counter=seq))
        # First frame is the synthetic gap, then the in-buffer replay.
        assert out[0].event_type == "gap"
        assert out[0].seq == 6
        assert out[0].payload == {
            "missed_from": 2,
            "missed_until": 2,
            "reason": "replay_buffer_overflow",
        }
        assert [e.seq for e in out[1:]] == [3, 4, 5]


# ── build_gap_envelope ────────────────────────────────────────────────────────


class TestBuildGapEnvelope:
    def test_payload_shape(self) -> None:
        gap = build_gap_envelope(
            seq=10,
            last_seq=2,
            server_oldest_seq=5,
            session_id="abc",
        )
        assert gap.event_type == "gap"
        assert gap.session_id == "abc"
        assert gap.payload["missed_from"] == 3
        assert gap.payload["missed_until"] == 4
        assert gap.payload["reason"] == "replay_buffer_overflow"


# ── HeartbeatTask ─────────────────────────────────────────────────────────────


class _RecordingWebSocket:
    """Minimal stand-in that records every ``send_text`` call.

    Avoids a real Starlette WebSocket dependency for unit-testing the
    heartbeat cadence; the integration test in ``test_server.py``
    exercises the full FastAPI WS path.
    """

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, message: str) -> None:
        self.sent.append(message)


class TestHeartbeatTask:
    def test_default_interval_is_30_seconds(self) -> None:
        assert HEARTBEAT_INTERVAL_SECONDS == 30.0

    def test_zero_interval_rejected(self) -> None:
        ws = _RecordingWebSocket()
        with pytest.raises(ValueError):
            HeartbeatTask(websocket=ws, seq_counter=[0], interval_seconds=0)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_emits_heartbeat_envelopes_on_cadence(self) -> None:
        ws = _RecordingWebSocket()
        seq = [0]
        # Use a 10ms interval so the test runs in <0.1s.
        async with HeartbeatTask(
            websocket=ws,  # type: ignore[arg-type]
            seq_counter=seq,
            session_id="sess",
            interval_seconds=0.01,
        ):
            # Allow at least 3 cycles to fire.
            await asyncio.sleep(0.05)

        assert len(ws.sent) >= 3
        for raw in ws.sent:
            env = WsEnvelope.model_validate_json(raw)
            assert env.event_type == "heartbeat"
            assert env.session_id == "sess"
            assert env.seq >= 1

    @pytest.mark.asyncio
    async def test_seq_counter_is_shared_with_caller(self) -> None:
        ws = _RecordingWebSocket()
        seq = [0]
        async with HeartbeatTask(
            websocket=ws,  # type: ignore[arg-type]
            seq_counter=seq,
            interval_seconds=0.01,
        ):
            await asyncio.sleep(0.03)
        # Counter must have advanced past 0 — heartbeat shares the
        # same counter as audit events so client gap detection works.
        assert seq[0] >= 1

    @pytest.mark.asyncio
    async def test_cancelled_cleanly_on_exit(self) -> None:
        ws = _RecordingWebSocket()
        seq = [0]
        # Big interval — task should be cancelled before any heartbeat.
        async with HeartbeatTask(
            websocket=ws,  # type: ignore[arg-type]
            seq_counter=seq,
            interval_seconds=10.0,
        ):
            await asyncio.sleep(0.01)
        # No heartbeats fired and no leaked task warnings.
        assert ws.sent == []
        assert seq[0] == 0
