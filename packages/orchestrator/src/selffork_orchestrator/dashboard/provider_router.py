"""FastAPI router for the Provider Auth UI (M5 — ADR-005 §M5-E).

Five endpoints + storage_state catalogue helpers. Browser-driven sign-in
flows are stubbed in M5: the route emits a session_id immediately and the
caller polls / subscribes to ``provider.auth.*`` audit events for progress.
Full OAuth orchestration (browser-use callback intercept) lands in the
follow-up Order 9 implementation work; this module owns the REST contract.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


def _serialise(record: ProviderRecord) -> ProviderView:
    return ProviderView(
        name=record.name,
        status=record.status,
        expires_at=record.expires_at.isoformat() if record.expires_at else None,
        last_sign_in=record.last_sign_in.isoformat() if record.last_sign_in else None,
        last_error=record.last_error,
        storage_state_path=record.storage_state_path,
    )


def build_provider_router(*, registry: ProviderRegistry) -> APIRouter:
    router = APIRouter(prefix="/api/providers", tags=["providers"])

    @router.get("", response_model=list[ProviderView])
    async def list_providers() -> list[ProviderView]:
        return [_serialise(r) for r in registry.list_records()]

    @router.post("/{name}/sign_in_start", response_model=SignInStartResponse)
    async def sign_in_start(name: str) -> SignInStartResponse:
        if name not in PROVIDER_NAMES:
            raise HTTPException(status_code=404, detail=f"unknown provider {name!r}")
        provider = name  # type: ignore[assignment]
        session_id = secrets.token_urlsafe(16)
        return SignInStartResponse(
            session_id=session_id,
            provider=provider,  # type: ignore[arg-type]
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
        record = registry.get(name)  # type: ignore[arg-type]
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
        return _serialise(registry.mark_disconnected(name))  # type: ignore[arg-type]

    return router
