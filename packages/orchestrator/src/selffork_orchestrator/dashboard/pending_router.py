"""FastAPI router for destructive-action pending confirmations.

Exposes the ``PendingConfirmationStore`` (Body pillar) over HTTP so
the cockpit can render the workspace-level "destructive action
pending" banner and let the operator approve/cancel.

ADR-006 §4.5 — soft confirmation, fail-safe NO, 4-hour default window.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from selffork_body.sandbox.pending_confirmations import (
    PendingConfirmation,
    PendingConfirmationStore,
)

_log = logging.getLogger(__name__)


def _audit_extended(
    entry: PendingConfirmation, *, hours: int, by: str
) -> None:
    """Best-effort log of a ``destructive_action_extended`` event.

    The orchestrator's per-session :class:`AuditLogger` is scoped to a
    Session — the dashboard process has no session context, so we emit
    a structured log line here. The JSONL audit (``op="extend"``) in
    PendingConfirmationStore remains the source of truth.
    """
    _log.info(
        "destructive_action_extended",
        extra={
            "id": entry.id,
            "category": entry.category_id,
            "workspace": entry.workspace_slug,
            "hours": hours,
            "by": by,
            "expires_at": entry.expires_at,
        },
    )


class ExtendRequest(BaseModel):
    hours: int = 2


class PendingConfirmationResponse(BaseModel):
    id: str
    workspace_slug: str | None
    category_id: str
    category_description: str
    command_summary: str
    asked_at: str
    expires_at: str
    time_left_seconds: int
    status: str


def _serialise(entry: PendingConfirmation) -> PendingConfirmationResponse:
    return PendingConfirmationResponse(
        id=entry.id,
        workspace_slug=entry.workspace_slug,
        category_id=entry.category_id,
        category_description=entry.category_description,
        command_summary=entry.command_summary,
        asked_at=entry.asked_at,
        expires_at=entry.expires_at,
        time_left_seconds=entry.time_left_seconds(),
        status=entry.status,
    )


def build_pending_router(*, store: PendingConfirmationStore) -> APIRouter:
    router = APIRouter(tags=["pending"])

    @router.get(
        "/api/pending-confirmations",
        response_model=list[PendingConfirmationResponse],
    )
    async def list_all() -> list[PendingConfirmationResponse]:
        """All pending confirmations (across every workspace)."""
        # Pull in any rows the ``selffork run`` producer wrote since we
        # last read (cross-process consistency — ADR-007 §4 S3).
        store.reload_from_disk()
        store.expire_stale()
        return [_serialise(p) for p in store.list_pending()]

    @router.get(
        "/api/pending-confirmations/count",
        response_model=int,
    )
    async def pending_count() -> int:
        """Cheap count endpoint for the topbar badge."""
        store.reload_from_disk()
        store.expire_stale()
        return len(store.list_pending())

    @router.get(
        "/api/workspaces/{slug}/pending-confirmations",
        response_model=list[PendingConfirmationResponse],
    )
    async def list_for_workspace(
        slug: str,
    ) -> list[PendingConfirmationResponse]:
        """Pending confirmations scoped to a single workspace."""
        store.reload_from_disk()
        store.expire_stale()
        return [
            _serialise(p)
            for p in store.list_pending(workspace_slug=slug)
        ]

    @router.post(
        "/api/pending-confirmations/{confirmation_id}/approve",
        response_model=PendingConfirmationResponse,
    )
    async def approve(confirmation_id: str) -> PendingConfirmationResponse:
        entry = store.approve(confirmation_id, by="operator-dashboard")
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown confirmation {confirmation_id}",
            )
        return _serialise(entry)

    @router.post(
        "/api/pending-confirmations/{confirmation_id}/cancel",
        response_model=PendingConfirmationResponse,
    )
    async def cancel(confirmation_id: str) -> PendingConfirmationResponse:
        entry = store.cancel(confirmation_id, by="operator-dashboard")
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown confirmation {confirmation_id}",
            )
        return _serialise(entry)

    @router.post(
        "/api/pending-confirmations/{confirmation_id}/extend",
        response_model=PendingConfirmationResponse,
    )
    async def extend(
        confirmation_id: str,
        payload: ExtendRequest,
    ) -> PendingConfirmationResponse:
        if payload.hours <= 0:
            raise HTTPException(
                status_code=400,
                detail="hours must be positive",
            )
        entry = store.extend(
            confirmation_id,
            hours=payload.hours,
            by="operator-dashboard",
        )
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown confirmation {confirmation_id}",
            )
        # ``destructive_action_extended`` audit row mirrors the store's
        # JSONL ``op="extend"`` line so per-session audit logs stay in
        # sync with the cross-process pending log (audit fix #13).
        _audit_extended(entry, hours=payload.hours, by="operator-dashboard")
        return _serialise(entry)

    return router
