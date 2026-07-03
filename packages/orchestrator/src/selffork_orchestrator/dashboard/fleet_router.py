"""FastAPI router for the body-daemon fleet (M5 — ADR-005 §M5-A).

Endpoints:

* ``POST /api/fleet/heartbeat`` — daemon heartbeat ingest.
* ``POST /api/fleet/state``     — CLI snapper-state delta.
* ``POST /api/fleet/register``  — register a new daemon (issue auth key).
* ``GET  /api/fleet/daemons``   — list registered daemons + status.
* ``DELETE /api/fleet/daemons/<id>`` — revoke + remove.

Persistence is a DuckDB-backed ``FleetRegistry``: the daemon roster and the
auth keys issued at registration survive an orchestrator restart. The store
keeps the exact async protocol the M5 in-memory registry exposed, so every
call site (the REST endpoints and the ``/ws/fleet`` route) is unchanged.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import duckdb
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
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


_FLEET_DDL = """
CREATE TABLE IF NOT EXISTS fleet_daemons (
    machine_id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    location_tier TEXT NOT NULL,
    version TEXT NOT NULL,
    auth_key TEXT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    last_heartbeat TIMESTAMPTZ,
    latency_ms INTEGER,
    online BOOLEAN NOT NULL DEFAULT FALSE,
    snapper_states_json TEXT NOT NULL DEFAULT '{}'
);
"""


def _default_fleet_db_path() -> Path:
    """Resolve the on-disk fleet registry database.

    Order mirrors selffork-mind's ``default_selffork_home``:

    1. ``SELFFORK_HOME`` environment variable.
    2. ``~/.selffork``.

    The registry file lives at ``<home>/fleet/registry.duckdb``.
    """
    env = os.environ.get("SELFFORK_HOME")
    home = Path(env).expanduser().resolve() if env else Path.home() / ".selffork"
    return home / "fleet" / "registry.duckdb"


def _ensure_utc(value: datetime) -> datetime:
    """Normalise a DuckDB ``TIMESTAMPTZ`` read-back to an aware UTC datetime.

    DuckDB may return naive or session-local datetimes; downstream comparisons
    (the ``list_records`` online cutoff) and ``isoformat`` need a stable
    aware-UTC value.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class FleetRegistry:
    """DuckDB-backed daemon registry. Serialised via an asyncio lock.

    The daemon roster and the auth keys issued at registration persist in a
    single-file DuckDB database, so a restarted orchestrator recovers the fleet
    it had already registered. Blocking DuckDB calls run on a worker thread
    (:func:`asyncio.to_thread`) so the event loop is never blocked, and the
    asyncio lock serialises access (DuckDB is single-writer).

    ``db_path`` defaults to ``<SELFFORK_HOME>/fleet/registry.duckdb``. Pass the
    literal ``":memory:"`` for an ephemeral, test-only database. The connection
    opens lazily on first use, so construction stays synchronous and cheap and
    the router factory / app lifespan need no ``await``.
    """

    def __init__(
        self,
        *,
        online_grace_sec: int = 60,
        db_path: str | Path | None = None,
    ) -> None:
        self._lock = asyncio.Lock()
        self._online_grace = online_grace_sec
        self._conn: duckdb.DuckDBPyConnection | None = None
        if db_path == ":memory:":
            self._db_path = ":memory:"
        elif db_path is not None:
            self._db_path = str(db_path)
        else:
            self._db_path = str(_default_fleet_db_path())
        # Per-machine outbound command queues. A queue buffers signed commands
        # until the daemon's WebSocket drains them, so a command dispatched
        # while a daemon is momentarily disconnected is delivered on reconnect.
        # These bind to the live event loop and are intentionally NOT persisted:
        # in-flight commands are meaningless across a restart.
        self._outbound: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    # ── connection / schema (blocking, run on a worker thread) ─────────

    def _open(self) -> duckdb.DuckDBPyConnection:
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(self._db_path)
        conn.execute(_FLEET_DDL)
        return conn

    async def _conn_locked(self) -> duckdb.DuckDBPyConnection:
        """Return the open connection, creating DB + schema on first use.

        Caller MUST hold ``self._lock``.
        """
        if self._conn is None:
            self._conn = await asyncio.to_thread(self._open)
        return self._conn

    async def close(self) -> None:
        """Close the DuckDB connection, releasing the file lock.

        Idempotent. A restarted process reopens the same ``db_path`` and
        recovers the persisted roster. The app lifespan may call this on
        shutdown; it is not required for durability (writes autocommit).
        """
        async with self._lock:
            if self._conn is not None:
                conn = self._conn
                self._conn = None
                await asyncio.to_thread(conn.close)

    async def register(
        self,
        *,
        machine_id: str,
        hostname: str,
        location_tier: str,
        version: str,
    ) -> DaemonRecord:
        async with self._lock:
            conn = await self._conn_locked()
            if await asyncio.to_thread(self._machine_exists, conn, machine_id):
                raise ValueError(f"machine_id {machine_id!r} already registered")
            record = DaemonRecord(
                machine_id=machine_id,
                hostname=hostname,
                location_tier=location_tier,
                version=version,
                auth_key=secrets.token_urlsafe(32),
                registered_at=datetime.now(UTC),
            )
            await asyncio.to_thread(self._insert, conn, record)
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
            conn = await self._conn_locked()
            row = await asyncio.to_thread(
                self._heartbeat_row,
                conn,
                machine_id,
                location_tier,
                version,
                latency_self_ms,
                datetime.now(UTC),
            )
            if row is None:
                raise KeyError(machine_id)
            return self._row_to_record(row)

    async def update_state(
        self, *, machine_id: str, cli: str, state: dict[str, Any]
    ) -> None:
        async with self._lock:
            conn = await self._conn_locked()
            updated = await asyncio.to_thread(
                self._apply_state, conn, machine_id, cli, state, datetime.now(UTC)
            )
            if not updated:
                raise KeyError(machine_id)

    async def list_records(self) -> list[DaemonRecord]:
        async with self._lock:
            conn = await self._conn_locked()
            rows = await asyncio.to_thread(self._fetch_all, conn)
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=self._online_grace)
        records: list[DaemonRecord] = []
        for row in rows:
            record = self._row_to_record(row)
            if record.last_heartbeat is None or record.last_heartbeat < cutoff:
                record.online = False
            records.append(record)
        return records

    async def revoke(self, machine_id: str) -> bool:
        async with self._lock:
            self._outbound.pop(machine_id, None)
            conn = await self._conn_locked()
            return await asyncio.to_thread(self._delete, conn, machine_id)

    async def get(self, machine_id: str) -> DaemonRecord | None:
        async with self._lock:
            conn = await self._conn_locked()
            return await asyncio.to_thread(self._fetch_one, conn, machine_id)

    def channel(self, machine_id: str) -> asyncio.Queue[dict[str, Any]]:
        """Return the machine's outbound command queue, creating it lazily.

        Called only from within the orchestrator event loop (the WebSocket
        handler and the dispatch endpoint), so the queue binds to that loop.
        """
        return self._outbound.setdefault(machine_id, asyncio.Queue())

    async def dispatch_command(
        self, machine_id: str, command: dict[str, Any]
    ) -> None:
        """Queue a signed command for delivery to a registered daemon.

        Raises ``KeyError`` when the machine is not registered.
        """
        async with self._lock:
            conn = await self._conn_locked()
            if not await asyncio.to_thread(self._machine_exists, conn, machine_id):
                raise KeyError(machine_id)
        self.channel(machine_id).put_nowait(command)

    # ── blocking DuckDB helpers (executed via asyncio.to_thread) ───────

    @staticmethod
    def _machine_exists(conn: duckdb.DuckDBPyConnection, machine_id: str) -> bool:
        rows = conn.execute(
            "SELECT 1 FROM fleet_daemons WHERE machine_id = ?", [machine_id]
        ).fetchall()
        return bool(rows)

    @staticmethod
    def _insert(conn: duckdb.DuckDBPyConnection, record: DaemonRecord) -> None:
        conn.execute(
            "INSERT INTO fleet_daemons ("
            "machine_id, hostname, location_tier, version, auth_key, "
            "registered_at, last_heartbeat, latency_ms, online, "
            "snapper_states_json"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                record.machine_id,
                record.hostname,
                record.location_tier,
                record.version,
                record.auth_key,
                record.registered_at,
                record.last_heartbeat,
                record.latency_ms,
                record.online,
                json.dumps(record.snapper_states),
            ],
        )

    @staticmethod
    def _heartbeat_row(
        conn: duckdb.DuckDBPyConnection,
        machine_id: str,
        location_tier: str,
        version: str,
        latency_ms: int | None,
        now: datetime,
    ) -> tuple[Any, ...] | None:
        rows = conn.execute(
            "UPDATE fleet_daemons SET "
            "location_tier = ?, version = ?, last_heartbeat = ?, "
            "latency_ms = ?, online = TRUE WHERE machine_id = ? "
            "RETURNING machine_id, hostname, location_tier, version, "
            "auth_key, registered_at, last_heartbeat, latency_ms, online, "
            "snapper_states_json",
            [location_tier, version, now, latency_ms, machine_id],
        ).fetchall()
        return rows[0] if rows else None

    @staticmethod
    def _apply_state(
        conn: duckdb.DuckDBPyConnection,
        machine_id: str,
        cli: str,
        state: dict[str, Any],
        now: datetime,
    ) -> bool:
        rows = conn.execute(
            "SELECT snapper_states_json FROM fleet_daemons WHERE machine_id = ?",
            [machine_id],
        ).fetchall()
        if not rows:
            return False
        states: dict[str, dict[str, Any]] = json.loads(cast(str, rows[0][0]))
        states[cli] = state
        conn.execute(
            "UPDATE fleet_daemons SET "
            "snapper_states_json = ?, last_heartbeat = ?, online = TRUE "
            "WHERE machine_id = ?",
            [json.dumps(states), now, machine_id],
        )
        return True

    @staticmethod
    def _fetch_all(conn: duckdb.DuckDBPyConnection) -> list[tuple[Any, ...]]:
        return conn.execute(
            "SELECT machine_id, hostname, location_tier, version, auth_key, "
            "registered_at, last_heartbeat, latency_ms, online, "
            "snapper_states_json FROM fleet_daemons ORDER BY registered_at"
        ).fetchall()

    @staticmethod
    def _fetch_one(
        conn: duckdb.DuckDBPyConnection, machine_id: str
    ) -> DaemonRecord | None:
        rows = conn.execute(
            "SELECT machine_id, hostname, location_tier, version, auth_key, "
            "registered_at, last_heartbeat, latency_ms, online, "
            "snapper_states_json FROM fleet_daemons WHERE machine_id = ?",
            [machine_id],
        ).fetchall()
        if not rows:
            return None
        return FleetRegistry._row_to_record(rows[0])

    @staticmethod
    def _delete(conn: duckdb.DuckDBPyConnection, machine_id: str) -> bool:
        rows = conn.execute(
            "DELETE FROM fleet_daemons WHERE machine_id = ? RETURNING machine_id",
            [machine_id],
        ).fetchall()
        return bool(rows)

    @staticmethod
    def _row_to_record(row: tuple[Any, ...]) -> DaemonRecord:
        last_heartbeat = row[6]
        return DaemonRecord(
            machine_id=cast(str, row[0]),
            hostname=cast(str, row[1]),
            location_tier=cast(str, row[2]),
            version=cast(str, row[3]),
            auth_key=cast(str, row[4]),
            registered_at=_ensure_utc(cast(datetime, row[5])),
            last_heartbeat=(
                _ensure_utc(cast(datetime, last_heartbeat))
                if last_heartbeat is not None
                else None
            ),
            latency_ms=cast("int | None", row[7]),
            online=bool(row[8]),
            snapper_states=cast(
                "dict[str, dict[str, Any]]", json.loads(cast(str, row[9]))
            ),
        )


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


class DispatchCommand(BaseModel):
    """A signed command the orchestrator pushes to a daemon over WebSocket.

    Mirrors the ``SignedCommand`` struct in
    ``internal/command_intake/intake.go``; the daemon re-verifies the HMAC.
    """

    command: str = Field(min_length=1, max_length=128)
    args: dict[str, Any] = Field(default_factory=dict)
    nonce: str = Field(min_length=1, max_length=128)
    timestamp: str = Field(min_length=1, max_length=64)
    signature: str = Field(min_length=1, max_length=256)


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

    @router.post("/dispatch/{machine_id}", status_code=202)
    async def dispatch(machine_id: str, payload: DispatchCommand) -> dict[str, str]:
        """Queue a signed command for delivery over the daemon's WebSocket."""
        try:
            await registry.dispatch_command(machine_id, payload.model_dump())
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail=f"unknown machine {exc.args[0]!r}"
            ) from exc
        return {"status": "queued"}

    # The daemon dials this WebSocket (see internal/command_intake/intake.go).
    # It lives OUTSIDE the /api/fleet REST prefix so the on-the-wire path is
    # exactly /ws/fleet/<machine_id>, matching the Go client's dial URL.
    outer = APIRouter()
    outer.include_router(router)

    @outer.websocket("/ws/fleet/{machine_id}")
    async def fleet_ws(websocket: WebSocket, machine_id: str) -> None:
        record = await registry.get(machine_id)
        if record is None:
            # Reject unregistered daemons before completing the handshake.
            await websocket.close(code=4404)
            return
        await websocket.accept()
        queue = registry.channel(machine_id)

        # Push queued commands while watching the same socket for the daemon's
        # disconnect, so teardown is prompt and no command is dropped.
        receive_task = asyncio.ensure_future(websocket.receive())
        try:
            while True:
                send_task = asyncio.ensure_future(queue.get())
                done, _ = await asyncio.wait(
                    {receive_task, send_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if send_task in done:
                    await websocket.send_json(send_task.result())
                else:
                    send_task.cancel()
                if receive_task in done:
                    message = receive_task.result()
                    if message["type"] == "websocket.disconnect":
                        break
                    # Inbound frames from the daemon are ignored for now.
                    receive_task = asyncio.ensure_future(websocket.receive())
        except WebSocketDisconnect:
            pass
        finally:
            receive_task.cancel()

    return outer
