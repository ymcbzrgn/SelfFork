"""FastAPI router for the body-daemon fleet (M5 — ADR-005 §M5-A).

Endpoints:

* ``POST /api/fleet/heartbeat`` — daemon heartbeat ingest.
* ``POST /api/fleet/state``     — CLI snapper-state delta.
* ``POST /api/fleet/register``  — register a new daemon (issue auth key).
* ``GET  /api/fleet/daemons``   — list registered daemons + status.
* ``DELETE /api/fleet/daemons/<id>`` — revoke + remove.

Persistence is a pluggable in-memory ``FleetRegistry`` for M5; production
deployments can swap in DuckDB-backed state via the same protocol.
"""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

__all__ = ["DaemonRecord", "FleetRegistry", "build_fleet_router"]


@dataclass
class DaemonRecord:
    machine_id: str
    hostname: str
    location_tier: str
    version: str
    auth_key: str
    registered_at: datetime
    last_heartbeat: datetime | None = None
    latency_ms: int | None = None
    online: bool = False
    snapper_states: dict[str, dict[str, Any]] = field(default_factory=dict)


class FleetRegistry:
    """In-memory daemon registry. Thread-safe via asyncio lock."""

    def __init__(self, *, online_grace_sec: int = 60) -> None:
        self._records: dict[str, DaemonRecord] = {}
        self._lock = asyncio.Lock()
        self._online_grace = online_grace_sec

    async def register(
        self,
        *,
        machine_id: str,
        hostname: str,
        location_tier: str,
        version: str,
    ) -> DaemonRecord:
        async with self._lock:
            if machine_id in self._records:
                raise ValueError(f"machine_id {machine_id!r} already registered")
            auth_key = secrets.token_urlsafe(32)
            record = DaemonRecord(
                machine_id=machine_id,
                hostname=hostname,
                location_tier=location_tier,
                version=version,
                auth_key=auth_key,
                registered_at=datetime.now(UTC),
            )
            self._records[machine_id] = record
            return record

    async def heartbeat(
        self,
        *,
        machine_id: str,
        location_tier: str,
        version: str,
        latency_self_ms: int | None,
    ) -> DaemonRecord:
        async with self._lock:
            record = self._records.get(machine_id)
            if record is None:
                raise KeyError(machine_id)
            record.location_tier = location_tier
            record.version = version
            record.last_heartbeat = datetime.now(UTC)
            record.latency_ms = latency_self_ms
            record.online = True
            return record

    async def update_state(self, *, machine_id: str, cli: str, state: dict[str, Any]) -> None:
        async with self._lock:
            record = self._records.get(machine_id)
            if record is None:
                raise KeyError(machine_id)
            record.snapper_states[cli] = state
            record.last_heartbeat = datetime.now(UTC)
            record.online = True

    async def list_records(self) -> list[DaemonRecord]:
        async with self._lock:
            now = datetime.now(UTC)
            cutoff = now - timedelta(seconds=self._online_grace)
            for record in self._records.values():
                if record.last_heartbeat is None or record.last_heartbeat < cutoff:
                    record.online = False
            return list(self._records.values())

    async def revoke(self, machine_id: str) -> bool:
        async with self._lock:
            return self._records.pop(machine_id, None) is not None


# ---------------------------------------------------------------------------
# Pydantic wire schemas
# ---------------------------------------------------------------------------


class HeartbeatRequest(BaseModel):
    machine_id: str = Field(min_length=1, max_length=100)
    location_tier: str = Field(default="auto", max_length=20)
    version: str = Field(default="0.0.0-dev", max_length=64)
    latency_self_ms: int | None = None
    sent_at: str | None = None


class StateUpdateRequest(BaseModel):
    machine_id: str = Field(min_length=1, max_length=100)
    cli: str = Field(min_length=1, max_length=64)
    state: dict[str, Any]
    sent_at: str | None = None


class RegisterRequest(BaseModel):
    machine_id: str = Field(min_length=1, max_length=100)
    hostname: str = Field(min_length=1, max_length=255)
    location_tier: str = Field(default="auto", max_length=20)
    version: str = Field(default="0.0.0-dev", max_length=64)


class DaemonView(BaseModel):
    machine_id: str
    hostname: str
    location_tier: str
    version: str
    online: bool
    latency_ms: int | None
    last_heartbeat: str | None
    registered_at: str
    snapper_clis: list[str]


def _serialise(record: DaemonRecord) -> DaemonView:
    return DaemonView(
        machine_id=record.machine_id,
        hostname=record.hostname,
        location_tier=record.location_tier,
        version=record.version,
        online=record.online,
        latency_ms=record.latency_ms,
        last_heartbeat=record.last_heartbeat.isoformat() if record.last_heartbeat else None,
        registered_at=record.registered_at.isoformat(),
        snapper_clis=sorted(record.snapper_states.keys()),
    )


def build_fleet_router(*, registry: FleetRegistry) -> APIRouter:
    router = APIRouter(prefix="/api/fleet", tags=["fleet"])

    @router.post("/register", status_code=201)
    async def register(payload: RegisterRequest) -> dict[str, str]:
        try:
            record = await registry.register(
                machine_id=payload.machine_id,
                hostname=payload.hostname,
                location_tier=payload.location_tier,
                version=payload.version,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"auth_key": record.auth_key}

    @router.post("/heartbeat", status_code=204)
    async def heartbeat(payload: HeartbeatRequest) -> None:
        try:
            await registry.heartbeat(
                machine_id=payload.machine_id,
                location_tier=payload.location_tier,
                version=payload.version,
                latency_self_ms=payload.latency_self_ms,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown machine {exc.args[0]!r}") from exc

    @router.post("/state", status_code=204)
    async def state_update(payload: StateUpdateRequest) -> None:
        try:
            await registry.update_state(
                machine_id=payload.machine_id,
                cli=payload.cli,
                state=payload.state,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown machine {exc.args[0]!r}") from exc

    @router.get("/daemons", response_model=list[DaemonView])
    async def list_daemons() -> list[DaemonView]:
        records = await registry.list_records()
        return [_serialise(r) for r in records]

    @router.delete("/daemons/{machine_id}", status_code=204)
    async def revoke(machine_id: str) -> None:
        ok = await registry.revoke(machine_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"unknown machine {machine_id!r}")

    return router
