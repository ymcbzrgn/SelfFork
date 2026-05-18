"""M-1 WebSocket protocol primitives — Order 2.

Single multiplexed FastAPI WS per session, with:

* **Sequence ID** (monotonic ``int`` per server-side stream) on every
  envelope so the client can detect dropped frames and request replay.
* **Bounded replay buffer** (``deque(maxlen=N)``) so a client that
  reconnects with ``?last_seq=N`` can resume without re-reading the
  audit JSONL from disk every time.
* **Application-level heartbeat** every 30 s so a TCP-half-open client
  notices the dead connection within one heartbeat instead of the OS
  socket timeout (multi-minute on macOS by default).

These primitives are shared between the existing ``/api/sessions/{id}/stream``
endpoint and the M4 cockpit's per-tab subscriptions; ``event_type`` is
how the client distinguishes audit events from quota / kanban / mind /
chat-token events when multiplexed onto one connection.

The protocol is wire-stable: clients only need to honour ``seq`` +
``event_type``; new ``event_type`` values are additive.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from typing import Literal

from fastapi import WebSocket
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DEFAULT_REPLAY_BUFFER_SIZE",
    "HEARTBEAT_INTERVAL_SECONDS",
    "WS_EVENT_TYPES",
    "BoundedReplayBuffer",
    "HeartbeatTask",
    "ReplayRegistry",
    "WsEnvelope",
    "WsEventType",
    "build_audit_envelope",
    "build_gap_envelope",
    "next_seq",
    "parse_last_seq",
    "replay_or_gap",
]

# Heartbeat cadence and replay buffer size. 30 s heartbeat is the
# default for assistant-ui / Inngest Realtime; 200 frames is enough
# for ~1 minute of audit-stream throughput on a busy session
# (autopilot + tools + Mind together rarely exceed 4 events/s).
HEARTBEAT_INTERVAL_SECONDS = 30.0
DEFAULT_REPLAY_BUFFER_SIZE = 200

WsEventType = Literal[
    "audit",  # selffork_shared.audit JSONL event forwarded as-is
    "kanban",  # KanbanResponse snapshot diff
    "quota",  # QuotaSnapshot snapshot
    "mind",  # ProvenanceEntry / mind_router event
    "chat.token",  # streamed assistant token
    "heartbeat",  # liveness ping (no payload)
    "gap",  # server-side notice of a buffer overflow gap
    # M5 — Body pillar + Fleet + Provider Auth UI envelope kinds (ADR-005 §M5-F).
    "fleet_status",  # daemon heartbeat / state delta broadcast
    "body_action",  # body.action.* audit event
    "body_observation",  # body.observation audit event (path ref, never bytes)
    "provider_auth_status",  # provider.auth.* / provider.token.* event
    # M6 — Talk surface (ADR-007 §4 S1): operator ↔ Self Jr message.
    "talk.message",
]

# Used by tests + downstream consumers (TS mirror generator) to
# enumerate the closed set without importing private internals.
WS_EVENT_TYPES: tuple[WsEventType, ...] = (
    "audit",
    "kanban",
    "quota",
    "mind",
    "chat.token",
    "heartbeat",
    "gap",
    "fleet_status",
    "body_action",
    "body_observation",
    "provider_auth_status",
    "talk.message",
)


class WsEnvelope(BaseModel):
    """One frame on the multiplexed WebSocket.

    ``seq`` is monotonic per connection (NOT per ``event_type``) so the
    client can detect *any* dropped frame, not just dropped audit ones.
    The server emits ``seq=0`` only for the very first frame on a fresh
    connection; reconnect-with-replay starts from ``last_seq+1``.
    """

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=0)
    event_type: WsEventType
    session_id: str | None = None
    project_slug: str | None = None
    payload: dict[str, object]
    ts: datetime


def next_seq(counter: list[int]) -> int:
    """Atomic-ish monotonic counter (single asyncio loop owns it).

    Using a one-element ``list`` instead of an ``int`` is the simplest
    "mutable container" pattern that avoids closure-rebinding bugs in
    callers that pass the counter around.
    """
    counter[0] += 1
    return counter[0]


class BoundedReplayBuffer:
    """Server-side replay window for WS reconnects.

    Holds the last ``maxlen`` envelopes by ``seq``. On reconnect the
    client sends ``?last_seq=N`` and we replay everything strictly
    greater than ``N``; if ``N`` is older than our oldest envelope we
    emit a synthetic ``gap`` frame so the client knows to backfill via
    the REST endpoint.
    """

    def __init__(self, *, maxlen: int = DEFAULT_REPLAY_BUFFER_SIZE) -> None:
        if maxlen <= 0:
            raise ValueError(f"maxlen must be > 0, got {maxlen}")
        self._buf: deque[WsEnvelope] = deque(maxlen=maxlen)
        self._maxlen = maxlen

    @property
    def maxlen(self) -> int:
        return self._maxlen

    @property
    def oldest_seq(self) -> int | None:
        return self._buf[0].seq if self._buf else None

    @property
    def newest_seq(self) -> int | None:
        return self._buf[-1].seq if self._buf else None

    def __len__(self) -> int:
        return len(self._buf)

    def append(self, envelope: WsEnvelope) -> None:
        """Append; oldest is silently dropped when full (``deque`` semantics)."""
        self._buf.append(envelope)

    def replay_from(self, last_seq: int) -> Iterator[WsEnvelope]:
        """Yield envelopes with ``seq > last_seq``, oldest-first.

        Yields nothing if the buffer is empty or ``last_seq`` is at/past
        the newest. Callers should check :meth:`has_gap_for` first to
        decide whether to emit a synthetic gap frame.
        """
        for env in self._buf:
            if env.seq > last_seq:
                yield env

    def has_gap_for(self, last_seq: int) -> bool:
        """``True`` if the buffer can't fully cover everything since ``last_seq``.

        Returns ``True`` when ``last_seq < oldest_seq - 1`` (we've evicted
        frames the client missed). Returns ``False`` when ``last_seq``
        is within the window or the buffer is empty.
        """
        if not self._buf:
            return False
        oldest = self._buf[0].seq
        # Client is up-to-date or ahead of buffer floor.
        return last_seq + 1 < oldest

    def snapshot(self) -> tuple[WsEnvelope, ...]:
        """Immutable view for tests + diagnostics."""
        return tuple(self._buf)


class HeartbeatTask:
    """Background task that emits ``event_type='heartbeat'`` envelopes.

    Used as an async context manager so the surrounding endpoint can't
    forget to cancel the loop on disconnect — a leaked task would keep
    the WebSocket reference alive and block GC of the audit tail
    iterator.
    """

    def __init__(
        self,
        *,
        websocket: WebSocket,
        seq_counter: list[int],
        session_id: str | None = None,
        project_slug: str | None = None,
        interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        self._ws = websocket
        self._seq = seq_counter
        self._session_id = session_id
        self._project_slug = project_slug
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> HeartbeatTask:
        self._task = asyncio.create_task(self._run(), name="ws_heartbeat")
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._task is None:
            return
        self._task.cancel()
        # Wait for the cancellation to land; ``CancelledError`` is the
        # expected outcome and is not a programming error here.
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval)
                envelope = WsEnvelope(
                    seq=next_seq(self._seq),
                    event_type="heartbeat",
                    session_id=self._session_id,
                    project_slug=self._project_slug,
                    payload={},
                    ts=datetime.now(UTC),
                )
                # ``send_text`` raises if the socket is closed; let it
                # propagate so the surrounding ``async with`` exits cleanly.
                await self._ws.send_text(envelope.model_dump_json())
        except asyncio.CancelledError:
            raise
        except Exception:
            # Don't crash the parent endpoint — the audit tail itself
            # will catch the next ``send_text`` and tear down. Heartbeat
            # is best-effort liveness, not authoritative.
            return


def parse_last_seq(raw: str | int | None) -> int:
    """Coerce a ``?last_seq=`` query value to ``int``; clamp negatives to 0.

    The endpoint accepts the parameter as ``str | int | None`` because
    Starlette's query-param coercion isn't strict about it. Garbage
    input clamps to 0 (which is "I want everything from the start")
    instead of raising — clients reconnecting after an upgrade may not
    have a valid ``last_seq`` and we'd rather show them all the events
    we still have than drop the WS.
    """
    if raw is None:
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def build_audit_envelope(
    *,
    seq: int,
    payload: dict[str, object],
    session_id: str,
    project_slug: str | None = None,
) -> WsEnvelope:
    """Wrap one audit JSONL event in the M-1 envelope."""
    return WsEnvelope(
        seq=seq,
        event_type="audit",
        session_id=session_id,
        project_slug=project_slug,
        payload=payload,
        ts=datetime.now(UTC),
    )


def build_gap_envelope(
    *,
    seq: int,
    last_seq: int,
    server_oldest_seq: int,
    session_id: str | None = None,
    project_slug: str | None = None,
) -> WsEnvelope:
    """Synthetic frame telling the client to backfill via REST.

    ``last_seq`` is what the client claimed; ``server_oldest_seq`` is
    the floor of our replay buffer. The client should fetch events
    ``[last_seq+1, server_oldest_seq-1]`` from the REST endpoint and
    splice them in.
    """
    return WsEnvelope(
        seq=seq,
        event_type="gap",
        session_id=session_id,
        project_slug=project_slug,
        payload={
            "missed_from": last_seq + 1,
            "missed_until": server_oldest_seq - 1,
            "reason": "replay_buffer_overflow",
        },
        ts=datetime.now(UTC),
    )


def replay_or_gap(
    buffer: BoundedReplayBuffer,
    *,
    last_seq: int,
    seq_counter: list[int],
    session_id: str | None = None,
    project_slug: str | None = None,
) -> Iterable[WsEnvelope]:
    """Yield the right resume sequence for a client at ``last_seq``.

    * If the buffer has a gap ⇒ one ``gap`` frame, then any envelopes
      we still have (newer than ``last_seq``).
    * Otherwise ⇒ replay everything strictly newer than ``last_seq``.
    * If the buffer is empty or the client is up-to-date ⇒ nothing.
    """
    if buffer.has_gap_for(last_seq):
        oldest = buffer.oldest_seq
        if oldest is not None:
            yield build_gap_envelope(
                seq=next_seq(seq_counter),
                last_seq=last_seq,
                server_oldest_seq=oldest,
                session_id=session_id,
                project_slug=project_slug,
            )
    yield from buffer.replay_from(last_seq)


class ReplayRegistry:
    """Process-level registry mapping ``stream_key`` → replay state.

    Keys the audit-stream / kanban-stream / mind-provenance / chat
    handlers share so a client reconnecting with ``?last_seq=N`` can
    actually resume — the previous Order 2 implementation allocated a
    fresh ``BoundedReplayBuffer`` per connection, which made the
    ``last_seq`` query parameter a no-op (the replay buffer was empty
    at the moment the new client connected).

    The registry is in-memory and process-scoped. Multi-worker
    deployments would need a Redis-backed implementation; today the
    cockpit dashboard runs single-process so a dict is sufficient.

    ``stream_key`` shape is the caller's choice but typically the
    canonical pattern is ``f"{kind}:{id}"`` — e.g.
    ``"audit:01HJ_session"`` or ``"kanban:my-project"``.
    """

    def __init__(self, *, maxlen: int = DEFAULT_REPLAY_BUFFER_SIZE) -> None:
        self._buffers: dict[str, BoundedReplayBuffer] = {}
        self._counters: dict[str, list[int]] = {}
        self._maxlen = maxlen

    def buffer(self, stream_key: str) -> BoundedReplayBuffer:
        existing = self._buffers.get(stream_key)
        if existing is not None:
            return existing
        buf = BoundedReplayBuffer(maxlen=self._maxlen)
        self._buffers[stream_key] = buf
        return buf

    def counter(self, stream_key: str) -> list[int]:
        existing = self._counters.get(stream_key)
        if existing is not None:
            return existing
        counter = [0]
        self._counters[stream_key] = counter
        return counter

    def append(self, stream_key: str, envelope: WsEnvelope) -> None:
        self.buffer(stream_key).append(envelope)

    def reset(self, stream_key: str | None = None) -> None:
        """Drop a single key's state (test helper) or every key."""
        if stream_key is None:
            self._buffers.clear()
            self._counters.clear()
            return
        self._buffers.pop(stream_key, None)
        self._counters.pop(stream_key, None)


# Module-level singleton — every router shares it. Tests can override
# by constructing their own ``ReplayRegistry`` and passing it through
# the router factories that accept a registry argument.
_DEFAULT_REGISTRY = ReplayRegistry()


def default_registry() -> ReplayRegistry:
    return _DEFAULT_REGISTRY
