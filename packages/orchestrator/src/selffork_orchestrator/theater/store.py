"""SQLite-backed event store for the Live Run Theater — S2.

The theater (ADR-007 §4 S2) is the Workspace "Live Run" surface. A
running round-loop produces a single ordered stream of events per
workspace — CLI output chunks and Self Jr thought summaries — which the
theater WebSocket tails and the snapshot endpoint lists. The store also
holds the live ``active_loops`` state behind ``GET /api/loop/active``.

The store lives in its own SQLite file (path supplied by the caller,
conventionally ``~/.selffork/theater/events.db``). SQLite is the right
fit for the same reason the Talk and chat branch stores use it: many
small writes plus cursored scans, it ships in the stdlib, and — crucially
— the on-disk file is the cross-process bridge: a ``selffork run``
process writes here and the separate dashboard process reads here.

Concurrency mirrors
:class:`~selffork_orchestrator.talk.store.TalkStore`: a single
:class:`asyncio.Lock` serialises writes and the shared connection runs
queries on a worker thread via :func:`anyio.to_thread.run_sync`, so the
dashboard event loop never blocks on disk I/O.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import anyio
from pydantic import BaseModel, ValidationError

from selffork_orchestrator.theater.models import (
    ActiveLoopRecord,
    CliOutputPayload,
    TheaterEvent,
    TheaterEventKind,
    ThoughtPayload,
)
from selffork_shared.errors import ConfigError

__all__ = ["TheaterStore", "open_theater_store", "theater_db_path"]


# A single table for events: the theater is one ordered stream of
# mixed-kind events per workspace. ``UNIQUE (workspace_slug, seq)`` is the
# composite index that serves every query (the per-workspace scan and the
# WS delta).
_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS theater_events (
    id TEXT PRIMARY KEY,
    workspace_slug TEXT NOT NULL,
    session_id TEXT,
    seq INTEGER NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (workspace_slug, seq)
);
"""

# Active-loop state — a separate table because it is mutable
# current-state, not the append-only event stream. Kept in the same DB so
# the dashboard process reads loop state a separate ``selffork run``
# process wrote (the store-tail cross-process bridge).
_ACTIVE_LOOPS_DDL = """
CREATE TABLE IF NOT EXISTS active_loops (
    session_id TEXT PRIMARY KEY,
    workspace_slug TEXT NOT NULL,
    workspace_name TEXT NOT NULL,
    cli TEXT NOT NULL,
    turn INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_thought TEXT
);
"""

# A loop whose row has not been touched within this window is treated as
# crashed — ``register_loop`` and each ``touch_loop`` refresh
# ``updated_at``.
_STALE_AFTER_SECONDS = 1800

# Payload validator per event kind — the store fails fast on a malformed
# payload rather than persisting garbage a consumer cannot render.
_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "cli_output": CliOutputPayload,
    "thought": ThoughtPayload,
}


def theater_db_path(projects_root: Path) -> Path:
    """The shared theater DB path, derived from the projects root.

    Both the round-loop process (``selffork run``) and the dashboard
    process (``selffork ui``) call this so they open the same file —
    the on-disk store is their only cross-process channel.
    """
    return projects_root.parent / "theater" / "events.db"


class TheaterStore:
    """SQLite-backed store for Live Run Theater events + active loops.

    All public methods are async; SQLite calls are dispatched to a worker
    thread so the dashboard's event loop never blocks on disk I/O. Schema
    is created on :meth:`setup`; :meth:`teardown` closes the connection.
    Both are idempotent.
    """

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = asyncio.Lock()
        self._conn: sqlite3.Connection | None = None

    async def setup(self) -> None:
        async with self._lock:
            if self._conn is not None:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await anyio.to_thread.run_sync(self._connect)
            await anyio.to_thread.run_sync(self._init_schema)

    def _connect(self) -> sqlite3.Connection:
        # WAL keeps reads non-blocking against the rare write, and
        # ``check_same_thread=False`` is safe because we serialise access
        # through ``self._lock`` and ``anyio.to_thread``.
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_schema(self) -> None:
        assert self._conn is not None  # noqa: S101
        self._conn.execute(_EVENTS_DDL)
        self._conn.execute(_ACTIVE_LOOPS_DDL)
        self._conn.commit()

    async def teardown(self) -> None:
        async with self._lock:
            if self._conn is not None:
                conn = self._conn
                self._conn = None
                await anyio.to_thread.run_sync(conn.close)

    # ── Events ────────────────────────────────────────────────────────

    async def append_event(
        self,
        *,
        workspace_slug: str,
        session_id: str | None,
        kind: TheaterEventKind,
        payload: dict[str, object],
    ) -> TheaterEvent:
        """Append a theater event and assign the next per-workspace ``seq``.

        ``payload`` is validated against the model for ``kind`` so the
        store never persists a payload a consumer cannot render. Raises
        :class:`ConfigError` for an empty ``workspace_slug``, an unknown
        ``kind``, or a malformed payload.
        """
        if not workspace_slug.strip():
            raise ConfigError("workspace_slug cannot be empty")
        model_cls = _PAYLOAD_MODELS.get(kind)
        if model_cls is None:
            raise ConfigError(f"unknown theater event kind {kind!r}")
        try:
            model_cls.model_validate(payload)
        except ValidationError as exc:
            raise ConfigError(
                f"malformed payload for theater event {kind!r}: {exc}"
            ) from exc
        event_id = uuid4()
        created_at = datetime.now(UTC)
        payload_json = json.dumps(payload)
        async with self._lock:
            self._require_open()
            seq = await anyio.to_thread.run_sync(
                self._insert_event,
                workspace_slug,
                event_id,
                session_id,
                kind,
                payload_json,
                created_at,
            )
        return TheaterEvent(
            id=event_id,
            workspace_slug=workspace_slug,
            session_id=session_id,
            seq=seq,
            kind=kind,
            payload=payload,
            created_at=created_at,
        )

    def _insert_event(
        self,
        workspace_slug: str,
        event_id: UUID,
        session_id: str | None,
        kind: TheaterEventKind,
        payload_json: str,
        created_at: datetime,
    ) -> int:
        """Insert one event in a single transaction and return its ``seq``."""
        assert self._conn is not None  # noqa: S101
        cur = self._conn.cursor()
        try:
            next_seq = cast(
                "int",
                cur.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM theater_events "
                    "WHERE workspace_slug = ?",
                    (workspace_slug,),
                ).fetchone()[0],
            )
            cur.execute(
                "INSERT INTO theater_events "
                "(id, workspace_slug, session_id, seq, kind, payload, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(event_id),
                    workspace_slug,
                    session_id,
                    next_seq,
                    kind,
                    payload_json,
                    created_at.isoformat(),
                ),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return next_seq

    async def list_events(
        self,
        workspace_slug: str,
        *,
        limit: int | None = None,
    ) -> list[TheaterEvent]:
        """Return a workspace's events in ``seq`` order (oldest first)."""
        async with self._lock:
            self._require_open()
            rows = await anyio.to_thread.run_sync(
                self._list_event_rows, workspace_slug, limit
            )
        return [self._row_to_event(r) for r in rows]

    def _list_event_rows(
        self,
        workspace_slug: str,
        limit: int | None,
    ) -> list[tuple[object, ...]]:
        assert self._conn is not None  # noqa: S101
        sql = (
            "SELECT id, workspace_slug, session_id, seq, kind, payload, "
            "created_at FROM theater_events WHERE workspace_slug = ? "
            "ORDER BY seq ASC"
        )
        params: tuple[object, ...] = (workspace_slug,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (workspace_slug, limit)
        return cast(
            "list[tuple[object, ...]]",
            self._conn.execute(sql, params).fetchall(),
        )

    async def list_events_after(
        self,
        workspace_slug: str,
        *,
        after_seq: int,
        limit: int = 1000,
    ) -> list[TheaterEvent]:
        """Return events with ``seq > after_seq`` — the WS delta query.

        ``after_seq=0`` returns the whole stream. The ``limit`` cap keeps
        a single WS poll bounded; typical deltas are a handful of events.
        """
        async with self._lock:
            self._require_open()
            rows = await anyio.to_thread.run_sync(
                self._list_events_after_rows,
                workspace_slug,
                after_seq,
                limit,
            )
        return [self._row_to_event(r) for r in rows]

    def _list_events_after_rows(
        self,
        workspace_slug: str,
        after_seq: int,
        limit: int,
    ) -> list[tuple[object, ...]]:
        assert self._conn is not None  # noqa: S101
        cur = self._conn.execute(
            "SELECT id, workspace_slug, session_id, seq, kind, payload, "
            "created_at FROM theater_events "
            "WHERE workspace_slug = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
            (workspace_slug, after_seq, limit),
        )
        return cast("list[tuple[object, ...]]", cur.fetchall())

    # ── Active loops ──────────────────────────────────────────────────

    async def register_loop(
        self,
        *,
        session_id: str,
        workspace_slug: str,
        workspace_name: str,
        cli: str,
        started_at: datetime | None = None,
    ) -> ActiveLoopRecord:
        """Record a round-loop as active (``turn`` 0).

        Idempotent — re-registering the same ``session_id`` replaces the
        row. Raises :class:`ConfigError` for an empty ``session_id`` or
        ``workspace_slug``.
        """
        if not session_id.strip():
            raise ConfigError("session_id cannot be empty")
        if not workspace_slug.strip():
            raise ConfigError("workspace_slug cannot be empty")
        now = datetime.now(UTC)
        record = ActiveLoopRecord(
            session_id=session_id,
            workspace_slug=workspace_slug,
            workspace_name=workspace_name,
            cli=cli,
            turn=0,
            started_at=started_at or now,
            updated_at=now,
            last_thought=None,
        )
        async with self._lock:
            self._require_open()
            await anyio.to_thread.run_sync(self._upsert_loop, record)
        return record

    def _upsert_loop(self, record: ActiveLoopRecord) -> None:
        assert self._conn is not None  # noqa: S101
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO active_loops "
                "(session_id, workspace_slug, workspace_name, cli, turn, "
                "started_at, updated_at, last_thought) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.session_id,
                    record.workspace_slug,
                    record.workspace_name,
                    record.cli,
                    record.turn,
                    record.started_at.isoformat(),
                    record.updated_at.isoformat(),
                    record.last_thought,
                ),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    async def touch_loop(
        self,
        *,
        session_id: str,
        turn: int,
        last_thought: str | None = None,
    ) -> None:
        """Advance an active loop's ``turn`` and refresh ``updated_at``.

        ``last_thought`` is updated only when provided — a turn with no
        narration keeps the previous thought. A touch for an unknown or
        already-cleared ``session_id`` is a silent no-op (it must not
        resurrect a loop that just ended).
        """
        updated_at = datetime.now(UTC)
        async with self._lock:
            self._require_open()
            await anyio.to_thread.run_sync(
                self._touch_loop,
                session_id,
                turn,
                last_thought,
                updated_at,
            )

    def _touch_loop(
        self,
        session_id: str,
        turn: int,
        last_thought: str | None,
        updated_at: datetime,
    ) -> None:
        assert self._conn is not None  # noqa: S101
        try:
            self._conn.execute(
                "UPDATE active_loops SET turn = ?, updated_at = ?, "
                "last_thought = COALESCE(?, last_thought) "
                "WHERE session_id = ?",
                (turn, updated_at.isoformat(), last_thought, session_id),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    async def clear_loop(self, session_id: str) -> None:
        """Remove a loop from the active set — called when it ends."""
        async with self._lock:
            self._require_open()
            await anyio.to_thread.run_sync(self._clear_loop, session_id)

    def _clear_loop(self, session_id: str) -> None:
        assert self._conn is not None  # noqa: S101
        try:
            self._conn.execute(
                "DELETE FROM active_loops WHERE session_id = ?",
                (session_id,),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    async def active_loop(
        self,
        *,
        stale_after_seconds: int = _STALE_AFTER_SECONDS,
    ) -> ActiveLoopRecord | None:
        """Return the most-recently-active loop, or ``None`` if idle.

        Backs ``GET /api/loop/active``. A loop untouched for longer than
        ``stale_after_seconds`` is treated as crashed and skipped.
        """
        async with self._lock:
            self._require_open()
            row = await anyio.to_thread.run_sync(
                self._fetch_active_loop, stale_after_seconds
            )
        return self._row_to_loop(row) if row is not None else None

    def _fetch_active_loop(
        self,
        stale_after_seconds: int,
    ) -> tuple[object, ...] | None:
        assert self._conn is not None  # noqa: S101
        threshold = datetime.now(UTC) - timedelta(
            seconds=stale_after_seconds
        )
        cur = self._conn.execute(
            "SELECT session_id, workspace_slug, workspace_name, cli, turn, "
            "started_at, updated_at, last_thought FROM active_loops "
            "WHERE updated_at > ? ORDER BY updated_at DESC LIMIT 1",
            (threshold.isoformat(),),
        )
        return cast("tuple[object, ...] | None", cur.fetchone())

    async def loop_for_workspace(
        self,
        workspace_slug: str,
        *,
        stale_after_seconds: int = _STALE_AFTER_SECONDS,
    ) -> ActiveLoopRecord | None:
        """Return the active loop for one workspace, or ``None``."""
        async with self._lock:
            self._require_open()
            row = await anyio.to_thread.run_sync(
                self._fetch_loop_for_workspace,
                workspace_slug,
                stale_after_seconds,
            )
        return self._row_to_loop(row) if row is not None else None

    def _fetch_loop_for_workspace(
        self,
        workspace_slug: str,
        stale_after_seconds: int,
    ) -> tuple[object, ...] | None:
        assert self._conn is not None  # noqa: S101
        threshold = datetime.now(UTC) - timedelta(
            seconds=stale_after_seconds
        )
        cur = self._conn.execute(
            "SELECT session_id, workspace_slug, workspace_name, cli, turn, "
            "started_at, updated_at, last_thought FROM active_loops "
            "WHERE workspace_slug = ? AND updated_at > ? "
            "ORDER BY updated_at DESC LIMIT 1",
            (workspace_slug, threshold.isoformat()),
        )
        return cast("tuple[object, ...] | None", cur.fetchone())

    # ── Helpers ───────────────────────────────────────────────────────

    def _require_open(self) -> None:
        if self._conn is None:
            raise ConfigError("TheaterStore is closed; call setup() first")

    def _row_to_event(self, row: Sequence[object]) -> TheaterEvent:
        return TheaterEvent(
            id=UUID(cast("str", row[0])),
            workspace_slug=cast("str", row[1]),
            session_id=cast("str | None", row[2]),
            seq=cast("int", row[3]),
            kind=cast("TheaterEventKind", row[4]),
            payload=cast(
                "dict[str, object]", json.loads(cast("str", row[5]))
            ),
            created_at=datetime.fromisoformat(cast("str", row[6])),
        )

    def _row_to_loop(self, row: Sequence[object]) -> ActiveLoopRecord:
        return ActiveLoopRecord(
            session_id=cast("str", row[0]),
            workspace_slug=cast("str", row[1]),
            workspace_name=cast("str", row[2]),
            cli=cast("str", row[3]),
            turn=cast("int", row[4]),
            started_at=datetime.fromisoformat(cast("str", row[5])),
            updated_at=datetime.fromisoformat(cast("str", row[6])),
            last_thought=cast("str | None", row[7]),
        )


@contextlib.asynccontextmanager
async def open_theater_store(db_path: Path):  # type: ignore[no-untyped-def]
    """Async context manager for tests + helpers."""
    store = TheaterStore(db_path=db_path)
    await store.setup()
    try:
        yield store
    finally:
        await store.teardown()
