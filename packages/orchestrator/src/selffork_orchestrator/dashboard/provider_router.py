"""FastAPI router for the Provider Auth UI (M5 — ADR-005 §M5-E).

Five endpoints + storage_state catalogue helpers. The sign_in_start /
refresh routes stay as REST stubs — S5 (ADR-007 §4) confirmed that
CLI-native sign-in is the way (operator runs ``<cli> login`` in the
terminal) — but S5 adds the operator-facing **alert** surface: when
something detects an expired session (snapper layer, CLI invocation
wrapper) it POSTs to ``/{name}/auth-expired`` and we fan that out as
a Telegram nudge via :class:`ProviderAuthMonitor`.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import anyio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from selffork_orchestrator.dashboard.provider_auth_monitor import (
    ProviderAuthMonitor,
)
from selffork_orchestrator.dashboard.provider_creds import (
    ProviderAuthStatus,
    detect_all,
)

# Resolves on-disk auth status for every provider (CLI-native sign-in,
# [[cli-provider-routing]]); injectable so tests don't touch the real
# home dir / keychain.
type CredsDetector = Callable[[], dict[str, ProviderAuthStatus]]

__all__ = [
    "ProviderName",
    "ProviderRecord",
    "ProviderRegistry",
    "build_provider_router",
]


ProviderName = Literal["claude_pro", "codex", "gemini", "opencode", "mmx"]
PROVIDER_NAMES: tuple[ProviderName, ...] = (
    "claude_pro",
    "codex",
    "gemini",
    "opencode",
    "mmx",
)


@dataclass
class ProviderRecord:
    name: ProviderName
    status: Literal["connected", "disconnected", "expired", "expiring_soon"] = "disconnected"
    expires_at: datetime | None = None
    last_sign_in: datetime | None = None
    last_error: str | None = None
    storage_state_path: str | None = None


class ProviderRegistry:
    """In-memory registry of provider auth status."""

    def __init__(self) -> None:
        self._records: dict[ProviderName, ProviderRecord] = {
            name: ProviderRecord(name=name) for name in PROVIDER_NAMES
        }

    def list_records(self) -> list[ProviderRecord]:
        return list(self._records.values())

    def get(self, name: ProviderName) -> ProviderRecord:
        return self._records[name]

    def mark_signed_in(
        self,
        name: ProviderName,
        *,
        storage_state_path: str | None = None,
        expires_at: datetime | None = None,
    ) -> ProviderRecord:
        record = self._records[name]
        record.status = "connected"
        record.last_sign_in = datetime.now(UTC)
        record.last_error = None
        record.expires_at = expires_at
        record.storage_state_path = storage_state_path
        return record

    def mark_disconnected(self, name: ProviderName) -> ProviderRecord:
        record = self._records[name]
        record.status = "disconnected"
        record.expires_at = None
        record.storage_state_path = None
        return record

    def mark_failed(self, name: ProviderName, error: str) -> ProviderRecord:
        record = self._records[name]
        record.last_error = error
        return record


# ---------------------------------------------------------------------------
# Wire schemas
# ---------------------------------------------------------------------------


class ProviderView(BaseModel):
    name: ProviderName
    status: Literal["connected", "disconnected", "expired", "expiring_soon"]
    expires_at: str | None
    last_sign_in: str | None
    last_error: str | None
    storage_state_path: str | None


class SignInStartResponse(BaseModel):
    session_id: str
    provider: ProviderName
    started_at: str


class AuthExpiredRequest(BaseModel):
    """Payload for ``POST /{name}/auth-expired`` — S5 alert hook."""

    model_config = ConfigDict(extra="forbid")

    reason: str = "auth expired"


class AuthExpiredResponse(BaseModel):
    """Outcome of ``/{name}/auth-expired`` (visible to the caller)."""

    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    alerted_at: str
    delivered: bool
    cooldown_skipped: bool


def _serialise(record: ProviderRecord) -> ProviderView:
    return ProviderView(
        name=record.name,
        status=record.status,
        expires_at=record.expires_at.isoformat() if record.expires_at else None,
        last_sign_in=record.last_sign_in.isoformat() if record.last_sign_in else None,
        last_error=record.last_error,
        storage_state_path=record.storage_state_path,
    )


def _serialise_with_disk(record: ProviderRecord, disk: ProviderAuthStatus | None) -> ProviderView:
    """Serialise a record with the on-disk auth status overlaid.

    On-disk creds win for ``status`` (the operator re-signs-in via the
    CLI, so disk is the freshest truth — even after an auth-expired
    alert). The registry still carries ``last_error`` (the most recent
    auth-expired reason) for visibility, and ``last_sign_in`` /
    ``storage_state_path`` if a dashboard flow ever set them.
    """
    if disk is None:
        return _serialise(record)
    expires_at = disk.expires_at or record.expires_at
    return ProviderView(
        name=record.name,
        status=disk.status,
        expires_at=expires_at.isoformat() if expires_at else None,
        last_sign_in=record.last_sign_in.isoformat() if record.last_sign_in else None,
        last_error=record.last_error,
        storage_state_path=record.storage_state_path,
    )


def build_provider_router(
    *,
    registry: ProviderRegistry,
    auth_monitor: ProviderAuthMonitor | None = None,
    creds_detector: CredsDetector | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/providers", tags=["providers"])
    monitor = auth_monitor or ProviderAuthMonitor()
    detector: CredsDetector = creds_detector or detect_all

    @router.get("", response_model=list[ProviderView])
    async def list_providers() -> list[ProviderView]:
        # On-disk creds are the source of truth for "signed in?" — the
        # operator authenticates CLI-natively, so the in-memory registry's
        # dashboard-sign-in record stays empty. Detection does a keychain
        # subprocess + file reads, so run it off the event loop.
        disk = await anyio.to_thread.run_sync(detector)
        return [_serialise_with_disk(r, disk.get(r.name)) for r in registry.list_records()]

    @router.post("/{name}/sign_in_start", response_model=SignInStartResponse)
    async def sign_in_start(name: str) -> SignInStartResponse:
        if name not in PROVIDER_NAMES:
            raise HTTPException(status_code=404, detail=f"unknown provider {name!r}")
        provider = name
        session_id = secrets.token_urlsafe(16)
        return SignInStartResponse(
            session_id=session_id,
            provider=provider,
            started_at=datetime.now(UTC).isoformat(),
        )

    @router.post("/{name}/refresh", status_code=202)
    async def refresh_token(name: str) -> dict[str, str]:
        if name not in PROVIDER_NAMES:
            raise HTTPException(status_code=404, detail=f"unknown provider {name!r}")
        return {"status": "refresh_requested"}

    @router.post("/{name}/disconnect", status_code=200)
    async def disconnect(name: str) -> ProviderView:
        if name not in PROVIDER_NAMES:
            raise HTTPException(status_code=404, detail=f"unknown provider {name!r}")
        record = registry.get(name)
        # M5 audit-fix wave — delete the on-disk storage_state JSON so the
        # next sign-in flow starts fresh (no ghost session cookies).
        if record.storage_state_path:
            from pathlib import Path

            path = Path(record.storage_state_path)
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
        return _serialise(registry.mark_disconnected(name))

    @router.post(
        "/{name}/auth-expired",
        response_model=AuthExpiredResponse,
        status_code=202,
    )
    async def auth_expired(
        name: str,
        payload: AuthExpiredRequest | None = None,
    ) -> AuthExpiredResponse:
        """Signal that the operator's session for this provider expired.

        Called by:

        * the snapper layer when it sees a 401 / 403 from the provider,
        * the CLI invocation wrapper when ``<cli>`` returns
          ``authentication_required``,
        * the operator manually from the Connections card if Self Jr
          loops on a dead session before the snapper notices.

        Fans the signal out to Telegram via
        :class:`ProviderAuthMonitor` (subject to cooldown so a
        hammering snapper doesn't spam the chat) and marks the
        registry record as failed so the Connections card reflects
        the state until the operator re-authenticates.
        """
        if name not in PROVIDER_NAMES:
            raise HTTPException(status_code=404, detail=f"unknown provider {name!r}")
        reason = (payload.reason if payload else "auth expired").strip()
        if not reason:
            reason = "auth expired"
        registry.mark_failed(name, f"auth_expired: {reason}")
        alert = await monitor.notify_auth_expired(name, reason)
        return AuthExpiredResponse(
            provider=name,
            alerted_at=alert.alerted_at.isoformat(),
            delivered=alert.delivered,
            cooldown_skipped=alert.cooldown_skipped,
        )

    return router
