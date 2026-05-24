"""FastAPI router for the workspace Live Run Theater (3-pane) — S2.

The Workspace "Live Run" tab surfaces a running round-loop: the CLI
output stream and Self Jr's compacted thought bubble. Both are served
from the theater event store
(:class:`~selffork_orchestrator.theater.store.TheaterStore`) — a SQLite
DB a separate ``selffork run`` process writes and this dashboard process
tails, the same store-tail decoupling the Talk and chat surfaces use.

The third pane, the screenshot timeline, has no producer in S2: the
round-loop is not wired to Body vision yet (ADR-007 §4 S2 scope note),
so ``screenshots`` is always empty and the pane renders an honest empty
state — never a fabricated frame.

Event types (``WsEnvelope.event_type``):
    snapshot           — full theater state, sent first on WS connect
    cli.output.append  — one new CLI output / jr-prompt chunk
    thought.new        — one new compacted Self Jr thought
    heartbeat          — keep-alive (every 30 s, ``HeartbeatTask``)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from selffork_orchestrator.theater.models import (
    ActiveLoopRecord,
    CliOutputPayload,
    TheaterEvent,
    ThoughtPayload,
)
from selffork_orchestrator.theater.store import TheaterStore
from selffork_shared.logging import get_logger

from .ws_protocol import (
    HeartbeatTask,
    WsEnvelope,
    default_registry,
    next_seq,
    parse_last_seq,
    replay_or_gap,
)

__all__ = ["build_loop_router", "build_theater_router"]

_log = get_logger(__name__)

# WS tail poll cadence — mirrors the Talk + chat routers.
_POLL_INTERVAL_SECONDS = 0.25


# ── Response models (mirrored by apps/web/lib/api.ts) ──────────────────


class CLIOutputChunk(BaseModel):
    id: str
    kind: Literal["stdout", "stderr", "system", "jr-prompt", "info"]
    text: str


class TheaterScreenshot(BaseModel):
    id: str
    at: str  # human-readable "HH:MM" or relative; clients format further
    source: Literal["browser", "mobile-emu", "desktop"] = "browser"
    vision_tier: Literal[1, 2, 3] = 1
    thumbnail_url: str | None = None
    preview_url: str | None = None
    active: bool = False


class JrThought(BaseModel):
    id: str
    summary: str
    raw: str | None = None


class TheaterSnapshot(BaseModel):
    """Snapshot of the workspace's Live Run Theater state."""

    active: bool
    cli: str | None
    turn: int
    duration_seconds: int
    output: list[CLIOutputChunk]
    screenshots: list[TheaterScreenshot]
    thoughts: list[JrThought]
    next_prompt: str | None = None


class ActiveLoopResponse(BaseModel):
    """Currently-active Self Jr loop, or absent if idle.

    Returned by ``GET /api/loop/active`` — the Dashboard's LiveLoopStatus
    hero card and (S7) the workspace transcript drawer's session
    discovery probe.
    """

    workspace_slug: str
    workspace_name: str
    cli: str
    turn: int
    started_at: str
    duration_seconds: int
    last_thought: str | None = None
    # S7 — exposed so the workspace's transcript drawer can fetch
    # ``GET /api/sessions/{session_id}/events`` for the currently-
    # running session.
    session_id: str


# ── Lazily-opened store handle ─────────────────────────────────────────


class _TheaterStoreHandle:
    """Lazily-opened :class:`TheaterStore`.

    Mirrors ``talk_router._TalkRouterState``: the store opens on the
    first request so constructing the app stays import-cheap and
    side-effect-free.
    """

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path
        self._store: TheaterStore | None = None
        self._lock = asyncio.Lock()

    async def store(self) -> TheaterStore:
        if self._store is not None:
            return self._store
        async with self._lock:
            if self._store is None:
                store = TheaterStore(db_path=self._db_path)
                await store.setup()
                self._store = store
            return self._store

    async def teardown(self) -> None:
        async with self._lock:
            if self._store is not None:
                await self._store.teardown()
                self._store = None


# ── Routers ────────────────────────────────────────────────────────────


def build_theater_router(*, projects_root: Path, db_path: Path) -> APIRouter:
    """Construct the ``/api/workspaces/{slug}/theater`` router.

    Args:
        projects_root: filesystem root where workspaces live; the slug
            must resolve to a directory or the endpoints 404.
        db_path: the theater event DB, shared with the ``selffork run``
            process (see ``theater.store.theater_db_path``).
    """
    router = APIRouter(prefix="/api/workspaces", tags=["theater"])
    handle = _TheaterStoreHandle(db_path=db_path)

    def _workspace_exists(slug: str) -> bool:
        return (projects_root / slug).is_dir()

    @router.get("/{slug}/theater/snapshot", response_model=TheaterSnapshot)
    async def snapshot(slug: str) -> TheaterSnapshot:
        """One-shot snapshot of the theater state for the first paint."""
        if not _workspace_exists(slug):
            raise HTTPException(
                status_code=404, detail=f"workspace {slug} not found"
            )
        store = await handle.store()
        snap, _ = await _build_snapshot(store, slug)
        return snap

    @router.websocket("/{slug}/theater/stream")
    async def stream(websocket: WebSocket, slug: str) -> None:
        """3-pane Live Run Theater event stream.

        Sends a ``snapshot`` envelope first, then ``cli.output.append`` /
        ``thought.new`` envelopes as the round-loop produces them, plus a
        30 s heartbeat. Reconnect with ``?last_seq=N`` replays buffered
        frames.
        """
        await websocket.accept()
        if not _workspace_exists(slug):
            await websocket.close(
                code=4404, reason=f"workspace {slug} not found"
            )
            return
        store = await handle.store()

        last_seq = parse_last_seq(websocket.query_params.get("last_seq"))
        registry = default_registry()
        stream_key = f"theater:{slug}"
        seq_counter = registry.counter(stream_key)
        replay_buffer = registry.buffer(stream_key)

        try:
            for env in replay_or_gap(
                replay_buffer,
                last_seq=last_seq,
                seq_counter=seq_counter,
            ):
                if env.event_type == "gap":
                    replay_buffer.append(env)
                await websocket.send_text(env.model_dump_json())

            snap, cursor = await _build_snapshot(store, slug)
            snap_envelope = WsEnvelope(
                seq=next_seq(seq_counter),
                event_type="snapshot",
                session_id=slug,
                payload=snap.model_dump(),
                ts=datetime.now(UTC),
            )
            replay_buffer.append(snap_envelope)
            await websocket.send_text(snap_envelope.model_dump_json())

            async with HeartbeatTask(
                websocket=websocket,
                seq_counter=seq_counter,
                session_id=slug,
            ):
                async for event in _tail_theater(
                    store, slug, after_seq=cursor
                ):
                    envelope = _event_to_envelope(
                        event, seq=next_seq(seq_counter)
                    )
                    replay_buffer.append(envelope)
                    await websocket.send_text(envelope.model_dump_json())
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _log.exception("theater_ws_failed", slug=slug)
            with contextlib.suppress(Exception):
                await websocket.send_text(
                    json.dumps({"error": f"{type(exc).__name__}: {exc}"})
                )

    return router


def build_loop_router(*, db_path: Path) -> APIRouter:
    """Construct the ``/api/loop`` router for active-loop introspection.

    Separate from the workspace-scoped theater router because the active
    loop is global — it might belong to any workspace, or to none.
    """
    router = APIRouter(prefix="/api/loop", tags=["loop"])
    handle = _TheaterStoreHandle(db_path=db_path)

    @router.get("/active", response_model=ActiveLoopResponse | None)
    async def get_active_loop() -> ActiveLoopResponse | None:
        """Return the active loop, or ``None`` if Self Jr is idle."""
        store = await handle.store()
        loop = await store.active_loop()
        if loop is None:
            return None
        return ActiveLoopResponse(
            workspace_slug=loop.workspace_slug,
            workspace_name=loop.workspace_name,
            cli=loop.cli,
            turn=loop.turn,
            started_at=loop.started_at.isoformat(),
            duration_seconds=_duration_seconds(loop),
            last_thought=loop.last_thought,
            session_id=loop.session_id,
        )

    return router


# ── Helpers ────────────────────────────────────────────────────────────


def _duration_seconds(loop: ActiveLoopRecord) -> int:
    elapsed = (datetime.now(UTC) - loop.started_at).total_seconds()
    return max(0, int(elapsed))


def _event_to_cli_chunk(event: TheaterEvent) -> CLIOutputChunk:
    payload = CliOutputPayload.model_validate(event.payload)
    return CLIOutputChunk(
        id=str(event.id), kind=payload.kind, text=payload.text
    )


def _event_to_thought(event: TheaterEvent) -> JrThought:
    payload = ThoughtPayload.model_validate(event.payload)
    return JrThought(
        id=str(event.id), summary=payload.summary, raw=payload.raw
    )


async def _build_snapshot(
    store: TheaterStore, slug: str
) -> tuple[TheaterSnapshot, int]:
    """Build the theater snapshot + return the high-water event ``seq``.

    The ``seq`` is the cursor the WS tails from so the live stream never
    re-sends an event already carried in the snapshot.
    """
    events = await store.list_events(slug)
    loop = await store.loop_for_workspace(slug)
    output = [
        _event_to_cli_chunk(e) for e in events if e.kind == "cli_output"
    ]
    thoughts = [
        _event_to_thought(e) for e in events if e.kind == "thought"
    ]
    cursor = events[-1].seq if events else 0
    snapshot = TheaterSnapshot(
        active=loop is not None,
        cli=loop.cli if loop is not None else None,
        turn=loop.turn if loop is not None else 0,
        duration_seconds=(
            _duration_seconds(loop) if loop is not None else 0
        ),
        output=output,
        screenshots=[],
        thoughts=thoughts,
        next_prompt=None,
    )
    return snapshot, cursor


def _event_to_envelope(event: TheaterEvent, *, seq: int) -> WsEnvelope:
    """Wrap one incremental theater event in a WS envelope."""
    if event.kind == "cli_output":
        return WsEnvelope(
            seq=seq,
            event_type="cli.output.append",
            session_id=event.workspace_slug,
            payload=_event_to_cli_chunk(event).model_dump(),
            ts=datetime.now(UTC),
        )
    return WsEnvelope(
        seq=seq,
        event_type="thought.new",
        session_id=event.workspace_slug,
        payload=_event_to_thought(event).model_dump(),
        ts=datetime.now(UTC),
    )


async def _tail_theater(
    store: TheaterStore,
    slug: str,
    *,
    after_seq: int,
    poll_interval_seconds: float = _POLL_INTERVAL_SECONDS,
) -> AsyncIterator[TheaterEvent]:
    """Yield theater events as they land — Phase 1 drains, Phase 2 polls.

    Mirrors the Talk router's tail: a monotonic ``seq`` cursor keeps each
    poll proportional to the delta, never re-scanning the whole stream.
    """
    cursor = after_seq

    async def _drain() -> list[TheaterEvent]:
        nonlocal cursor
        events = await store.list_events_after(slug, after_seq=cursor)
        if events:
            cursor = events[-1].seq
        return events

    for event in await _drain():
        yield event
    while True:
        await asyncio.sleep(poll_interval_seconds)
        for event in await _drain():
            yield event
