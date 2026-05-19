"""FastAPI router for the workspace Live Run Theater (3-pane).

The Workspace tab "Live Run" surfaces three synchronized panes — CLI
output stream, vision screenshot timeline, and Self Jr's compacted
thought bubble. This module ships the endpoint scaffold and protocol
envelope shape; the event producer (snappers + Body vision + Speaker
reasoning surface) wires in during M6.5.

Event types (``envelope.event_type``):
    snapshot — initial workspace theater state on connect
    cli.output.append — new CLI stdout/stderr chunk
    screenshot.new — Body vision driver captured a frame
    thought.new — Speaker emitted a compacted thought summary
    next_prompt.preview — next prompt being composed
    cli.switch — CLI router rotated to a different provider
    alert.new — destructive pending / quota low / error
    session.end — active session terminated
    heartbeat — keep-alive (every 30s, emitted by ``HeartbeatTask``)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import structlog
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .ws_protocol import HeartbeatTask, default_registry, next_seq

_log = structlog.get_logger(__name__)


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


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _empty_snapshot() -> TheaterSnapshot:
    return TheaterSnapshot(
        active=False,
        cli=None,
        turn=0,
        duration_seconds=0,
        output=[],
        screenshots=[],
        thoughts=[],
        next_prompt=None,
    )


def build_theater_router(*, projects_root: Path) -> APIRouter:
    """Construct the /api/workspaces/{slug}/theater router.

    Args:
        projects_root: filesystem root where workspaces live (e.g.
            ``~/.selffork/projects/``). The slug must resolve to a
            directory or the WS / HTTP snapshot endpoints 404.
    """
    router = APIRouter(prefix="/api/workspaces", tags=["theater"])

    def _workspace_exists(slug: str) -> bool:
        return (projects_root / slug).is_dir()

    @router.get("/{slug}/theater/snapshot", response_model=TheaterSnapshot)
    async def snapshot(slug: str) -> TheaterSnapshot:
        """One-shot snapshot of the theater state.

        Useful for clients without WebSocket support or for the first
        paint of the Workspace tab. M6.5 will read live event-producer
        state; for now we return an empty idle snapshot.
        """
        if not _workspace_exists(slug):
            raise HTTPException(
                status_code=404, detail=f"workspace {slug} not found"
            )
        return _empty_snapshot()

    @router.websocket("/{slug}/theater/stream")
    async def stream(websocket: WebSocket, slug: str) -> None:
        """3-pane Live Run Theater event stream.

        Sends ``snapshot`` as the first envelope, then a 30 s heartbeat
        until the client disconnects. Real producers append CLI output,
        screenshot, and thought envelopes via the event bus (M6.5).
        """
        await websocket.accept()
        if not _workspace_exists(slug):
            await websocket.close(
                code=4404, reason=f"workspace {slug} not found"
            )
            return

        registry = default_registry()
        stream_key = f"theater:{slug}"
        seq_counter = registry.counter(stream_key)

        initial_envelope: dict[str, Any] = {
            "event_type": "snapshot",
            "session_id": slug,
            "seq": next_seq(seq_counter),
            "ts": _utc_now_iso(),
            "payload": _empty_snapshot().model_dump(),
        }

        try:
            await websocket.send_text(json.dumps(initial_envelope))
            async with HeartbeatTask(
                websocket=websocket,
                seq_counter=seq_counter,
                session_id=slug,
            ):
                # Block until disconnect — event producer wires in M6.5.
                await asyncio.Event().wait()
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


class ActiveLoopResponse(BaseModel):
    """Currently-active Self Jr loop, or absent if idle.

    Returned by ``GET /api/loop/active``. Used by the Dashboard's
    LiveLoopStatus hero card.
    """

    workspace_slug: str
    workspace_name: str
    cli: str
    turn: int
    started_at: str
    duration_seconds: int
    last_thought: str | None = None


def build_loop_router() -> APIRouter:
    """Construct the /api/loop router for active-loop introspection.

    Separate from the workspace-scoped theater router because the
    *active* loop is global (one per Self Jr instance) — it might
    belong to any workspace, or to no workspace if Self Jr is idle.
    """
    router = APIRouter(prefix="/api/loop", tags=["loop"])

    @router.get("/active", response_model=ActiveLoopResponse | None)
    async def get_active_loop() -> ActiveLoopResponse | None:
        """Return the active loop, or ``None`` if Self Jr is idle.

        MV: always returns ``None``. M6.5 derives from the tmux
        session registry + the most-recent session's audit log.
        """
        return None

    return router
