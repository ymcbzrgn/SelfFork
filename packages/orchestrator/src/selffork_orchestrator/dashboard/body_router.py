"""FastAPI router for the Body pillar runtime control plane (M5 — ADR-005 §M5-D2).

Endpoints:

* ``GET    /api/body/sessions``                  — list active body sessions.
* ``GET    /api/body/sessions/{session_id}``     — single session detail.
* ``POST   /api/body/sessions/{session_id}/stop``— SIGKILL via watchdog.
* ``POST   /api/body/permissions/{request_id}``  — operator approve/deny.

The router is mounted by the dashboard server when a :class:`BodyWatchdog` and
optional :class:`PermissionWarden` registry have been wired. Tests inject
stubs through :func:`build_body_router` to exercise REST behaviour without
booting the orchestrator.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from selffork_body.sandbox import BodyWatchdog, PermissionWarden

__all__ = ["build_body_router"]


class StopBodyRequest(BaseModel):
    reason: str = Field(default="operator_stop", min_length=1, max_length=200)


class PermissionDecisionRequest(BaseModel):
    approved: bool
    reason: str = Field(default="operator_decision", min_length=1, max_length=200)


class BodySessionView(BaseModel):
    session_id: str
    pid: int | None
    started_at: str
    last_activity: str
    max_duration_sec: int
    idle_timeout_sec: int
    killed: bool
    kill_reason: str | None


def _serialise(session) -> BodySessionView:  # type: ignore[no-untyped-def]
    return BodySessionView(
        session_id=session.session_id,
        pid=session.pid,
        started_at=session.started_at.isoformat(),
        last_activity=session.last_activity.isoformat(),
        max_duration_sec=session.max_duration_sec,
        idle_timeout_sec=session.idle_timeout_sec,
        killed=session.killed,
        kill_reason=session.kill_reason,
    )


def build_body_router(
    *,
    watchdog: BodyWatchdog,
    warden_registry: dict[str, PermissionWarden] | None = None,
) -> APIRouter:
    """Construct the body router bound to a watchdog instance.

    ``warden_registry`` maps ``session_id`` → :class:`PermissionWarden` so
    operator decisions can resolve the right pending future. The orchestrator
    populates this mapping at session lifecycle.
    """
    router = APIRouter(prefix="/api/body", tags=["body"])
    wardens = warden_registry if warden_registry is not None else {}

    @router.get("/sessions", response_model=list[BodySessionView])
    async def list_sessions() -> list[BodySessionView]:
        return [_serialise(s) for s in watchdog.list_sessions()]

    @router.get("/sessions/{session_id}", response_model=BodySessionView)
    async def get_session(session_id: str) -> BodySessionView:
        for session in watchdog.list_sessions():
            if session.session_id == session_id:
                return _serialise(session)
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")

    @router.post("/sessions/{session_id}/stop", status_code=202)
    async def stop_session(
        session_id: str, payload: StopBodyRequest
    ) -> dict[str, Literal["killed", "already_killed", "not_found"]]:
        for session in watchdog.list_sessions():
            if session.session_id != session_id:
                continue
            if session.killed:
                return {"status": "already_killed"}
            killed = watchdog.kill_session(session_id, payload.reason)
            return {"status": "killed" if killed else "not_found"}
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")

    @router.post("/permissions/{request_id}", status_code=200)
    async def decide_permission(
        request_id: str, payload: PermissionDecisionRequest
    ) -> dict[str, bool | str]:
        for warden in wardens.values():
            ok = await warden.operator_decide(
                request_id, approved=payload.approved, reason=payload.reason
            )
            if ok:
                return {"matched": True, "decision": "approved" if payload.approved else "deny"}
        raise HTTPException(status_code=404, detail=f"request {request_id} not pending")

    return router
