"""SQLite-backed branch + chat-message store — Order 4.

Per-project DB at ``~/.selffork/projects/<slug>/chat/branches.db``.
SQLite (not DuckDB) because the access pattern is many small
upserts + per-branch list scans; SQLite's row-store is a better fit
than DuckDB's columnar layout for this workload, and we already
ship sqlite via the stdlib (no extra dep).

Concurrency: single :class:`asyncio.Lock` serialises writes; the
shared connection runs queries on a worker thread via
:func:`anyio.to_thread.run_sync`. The orchestrator is single-tenant
so write contention is bounded to "operator + Jr writing
back-to-back", which the lock comfortably handles.
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import anyio

from selffork_orchestrator.chat.branch_model import (
    Branch,
    ChatMessage,
    MessageRole,
)
from selffork_shared.errors import ConfigError

__all__ = ["BranchStore"]


_BRANCHES_DDL = """
CREATE TABLE IF NOT EXISTS branches (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    parent_branch_id TEXT,
    fork_message_id TEXT,
    label TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

_MESSAGES_DDL = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    branch_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    parent_message_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);
"""

_INDICES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_branches_session_id ON branches(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_messages_branch_id ON messages(branch_id);",
    "CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);",
)


_VALID_ROLES: frozenset[str] = frozenset({"user", "assistant", "tool"})


class BranchStore:
    """SQLite-backed store for branches + chat messages.

    All public methods are async; SQLite calls are dispatched to a
    worker thread so the dashboard's event loop never blocks on disk
    I/O. Schema is created on :meth:`setup`; :meth:`teardown` closes
    the connection. Both are idempotent.
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
        # WAL mode keeps reads non-blocking against the rare write,
        # and ``check_same_thread=False`` is safe because we serialise
        # access through ``self._lock`` and ``anyio.to_thread``.
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_schema(self) -> None:
        assert self._conn is not None  # noqa: S101
        self._conn.execute(_BRANCHES_DDL)
        self._conn.execute(_MESSAGES_DDL)
        for ddl in _INDICES:
            self._conn.execute(ddl)
        self._conn.commit()

    async def teardown(self) -> None:
        async with self._lock:
            if self._conn is not None:
                conn = self._conn
                self._conn = None
                await anyio.to_thread.run_sync(conn.close)

    # ── Branches ──────────────────────────────────────────────────────

    async def create_branch(
        self,
        *,
        session_id: str,
        label: str,
        parent_branch_id: UUID | None = None,
        fork_message_id: UUID | None = None,
        activate: bool = True,
    ) -> Branch:
        """Insert a new branch.

        When ``activate`` is true the new branch becomes the session's
        active one (any previous active branch loses the flag in the
        same transaction). The first branch on a session is always
        created with ``activate=True`` so the cockpit can render
        immediately.
        """
        if not label.strip():
            raise ConfigError("branch label cannot be empty")
        branch = Branch(
            id=uuid4(),
            session_id=session_id,
            parent_branch_id=parent_branch_id,
            fork_message_id=fork_message_id,
            label=label,
            is_active=activate,
            created_at=datetime.now(UTC),
        )
        async with self._lock:
            self._require_open()
            await anyio.to_thread.run_sync(self._insert_branch, branch, activate)
        return branch

    def _insert_branch(self, branch: Branch, activate: bool) -> None:
        assert self._conn is not None  # noqa: S101
        cur = self._conn.cursor()
        try:
            if activate:
                cur.execute(
                    "UPDATE branches SET is_active = 0 WHERE session_id = ?",
                    (branch.session_id,),
                )
            cur.execute(
                "INSERT INTO branches "
                "(id, session_id, parent_branch_id, fork_message_id, label, "
                "is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(branch.id),
                    branch.session_id,
                    str(branch.parent_branch_id) if branch.parent_branch_id else None,
                    str(branch.fork_message_id) if branch.fork_message_id else None,
                    branch.label,
                    1 if branch.is_active else 0,
                    branch.created_at.isoformat(),
                ),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    async def list_branches(self, session_id: str) -> list[Branch]:
        async with self._lock:
            self._require_open()
            rows = await anyio.to_thread.run_sync(self._list_branch_rows, session_id)
        return [self._row_to_branch(r) for r in rows]

    def _list_branch_rows(self, session_id: str) -> list[tuple[object, ...]]:
        assert self._conn is not None  # noqa: S101
        cur = self._conn.execute(
            "SELECT id, session_id, parent_branch_id, fork_message_id, label, "
            "is_active, created_at FROM branches WHERE session_id = ? "
            "ORDER BY created_at ASC",
            (session_id,),
        )
        # sqlite3 row tuples are typed ``Any`` upstream; cast pins them
        # to the declared shape so mypy --strict stays clean.
        return cast("list[tuple[object, ...]]", cur.fetchall())

    async def get_branch(self, branch_id: UUID) -> Branch | None:
        async with self._lock:
            self._require_open()
            row = await anyio.to_thread.run_sync(self._fetch_branch, branch_id)
        return self._row_to_branch(row) if row is not None else None

    def _fetch_branch(self, branch_id: UUID) -> tuple[object, ...] | None:
        assert self._conn is not None  # noqa: S101
        cur = self._conn.execute(
            "SELECT id, session_id, parent_branch_id, fork_message_id, label, "
            "is_active, created_at FROM branches WHERE id = ?",
            (str(branch_id),),
        )
        return cast("tuple[object, ...] | None", cur.fetchone())

    async def get_active_branch(self, session_id: str) -> Branch | None:
        async with self._lock:
            self._require_open()
            row = await anyio.to_thread.run_sync(self._fetch_active_row, session_id)
        return self._row_to_branch(row) if row is not None else None

    def _fetch_active_row(self, session_id: str) -> tuple[object, ...] | None:
        assert self._conn is not None  # noqa: S101
        cur = self._conn.execute(
            "SELECT id, session_id, parent_branch_id, fork_message_id, label, "
            "is_active, created_at FROM branches "
            "WHERE session_id = ? AND is_active = 1",
            (session_id,),
        )
        return cast("tuple[object, ...] | None", cur.fetchone())

    async def set_active_branch(
        self,
        session_id: str,
        branch_id: UUID,
    ) -> Branch:
        """Atomically flip the active flag to ``branch_id``.

        Raises :class:`ConfigError` when the branch belongs to a
        different session — guards against cross-session writes the
        cockpit could trigger by replaying a stale URL.
        """
        async with self._lock:
            self._require_open()
            updated = await anyio.to_thread.run_sync(self._update_active, session_id, branch_id)
        if updated is None:
            raise ConfigError(
                f"branch {branch_id!s} not found in session {session_id!r}",
            )
        return self._row_to_branch(updated)

    def _update_active(
        self,
        session_id: str,
        branch_id: UUID,
    ) -> tuple[object, ...] | None:
        assert self._conn is not None  # noqa: S101
        cur = self._conn.cursor()
        try:
            row = cur.execute(
                "SELECT id, session_id FROM branches WHERE id = ?",
                (str(branch_id),),
            ).fetchone()
            if row is None or row[1] != session_id:
                self._conn.rollback()
                return None
            cur.execute(
                "UPDATE branches SET is_active = 0 WHERE session_id = ?",
                (session_id,),
            )
            cur.execute(
                "UPDATE branches SET is_active = 1 WHERE id = ?",
                (str(branch_id),),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        result = cur.execute(
            "SELECT id, session_id, parent_branch_id, fork_message_id, label, "
            "is_active, created_at FROM branches WHERE id = ?",
            (str(branch_id),),
        ).fetchone()
        return cast("tuple[object, ...] | None", result)

    # ── Messages ──────────────────────────────────────────────────────

    async def append_message(
        self,
        *,
        branch_id: UUID,
        role: MessageRole,
        content: str,
        parent_message_id: UUID | None = None,
    ) -> ChatMessage:
        if role not in _VALID_ROLES:
            raise ConfigError(f"invalid role {role!r}")
        if not content.strip():
            raise ConfigError("message content cannot be empty")
        message = ChatMessage(
            id=uuid4(),
            branch_id=branch_id,
            role=role,
            content=content,
            parent_message_id=parent_message_id,
            created_at=datetime.now(UTC),
        )
        async with self._lock:
            self._require_open()
            await anyio.to_thread.run_sync(self._insert_message, message)
        return message

    def _insert_message(self, message: ChatMessage) -> None:
        assert self._conn is not None  # noqa: S101
        try:
            self._conn.execute(
                "INSERT INTO messages "
                "(id, branch_id, role, content, parent_message_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(message.id),
                    str(message.branch_id),
                    message.role,
                    message.content,
                    str(message.parent_message_id) if message.parent_message_id else None,
                    message.created_at.isoformat(),
                ),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    async def list_messages(
        self,
        branch_id: UUID,
        *,
        limit: int | None = None,
    ) -> list[ChatMessage]:
        async with self._lock:
            self._require_open()
            rows = await anyio.to_thread.run_sync(self._list_message_rows, branch_id, limit)
        return [self._row_to_message(r) for r in rows]

    async def list_messages_after(
        self,
        branch_id: UUID,
        *,
        after: datetime | None,
        limit: int = 1000,
    ) -> list[ChatMessage]:
        """Return messages with ``created_at > after`` (delta query).

        Used by ``_tail_session_messages`` so the WS poll never
        re-scans the full branch history. ``after=None`` returns all
        rows (initial drain). The ``limit=1000`` cap is generous —
        typical poll deltas are 1-2 messages; the cap exists to keep
        a single tick bounded against pathological backlogs.
        """
        async with self._lock:
            self._require_open()
            rows = await anyio.to_thread.run_sync(
                self._list_messages_after_rows,
                branch_id,
                after,
                limit,
            )
        return [self._row_to_message(r) for r in rows]

    def _list_message_rows(
        self,
        branch_id: UUID,
        limit: int | None,
    ) -> list[tuple[object, ...]]:
        assert self._conn is not None  # noqa: S101
        sql = (
            "SELECT id, branch_id, role, content, parent_message_id, created_at "
            "FROM messages WHERE branch_id = ? ORDER BY created_at ASC"
        )
        params: tuple[object, ...] = (str(branch_id),)
        if limit is not None:
            sql += " LIMIT ?"
            params = (str(branch_id), limit)
        return cast(
            "list[tuple[object, ...]]",
            self._conn.execute(sql, params).fetchall(),
        )

    def _list_messages_after_rows(
        self,
        branch_id: UUID,
        after: datetime | None,
        limit: int,
    ) -> list[tuple[object, ...]]:
        assert self._conn is not None  # noqa: S101
        if after is None:
            sql = (
                "SELECT id, branch_id, role, content, parent_message_id, "
                "created_at FROM messages WHERE branch_id = ? "
                "ORDER BY created_at ASC LIMIT ?"
            )
            params: tuple[object, ...] = (str(branch_id), limit)
        else:
            sql = (
                "SELECT id, branch_id, role, content, parent_message_id, "
                "created_at FROM messages "
                "WHERE branch_id = ? AND created_at > ? "
                "ORDER BY created_at ASC LIMIT ?"
            )
            params = (str(branch_id), after.isoformat(), limit)
        return cast(
            "list[tuple[object, ...]]",
            self._conn.execute(sql, params).fetchall(),
        )

    async def get_message(self, message_id: UUID) -> ChatMessage | None:
        async with self._lock:
            self._require_open()
            row = await anyio.to_thread.run_sync(self._fetch_message, message_id)
        return self._row_to_message(row) if row is not None else None

    def _fetch_message(
        self,
        message_id: UUID,
    ) -> tuple[object, ...] | None:
        assert self._conn is not None  # noqa: S101
        cur = self._conn.execute(
            "SELECT id, branch_id, role, content, parent_message_id, created_at "
            "FROM messages WHERE id = ?",
            (str(message_id),),
        )
        return cast("tuple[object, ...] | None", cur.fetchone())

    async def fork_from_message(
        self,
        *,
        session_id: str,
        message_id: UUID,
        label: str,
        activate: bool = True,
    ) -> tuple[Branch, list[ChatMessage]]:
        """Create a new branch that mirrors history up to ``message_id``.

        Returns the new branch + the copied prefix. Caller appends the
        operator's edited message on top via :meth:`append_message`.
        Raises :class:`ConfigError` when ``message_id`` is unknown or
        belongs to a different session's branch.
        """
        message = await self.get_message(message_id)
        if message is None:
            raise ConfigError(f"message {message_id!s} not found")
        parent_branch = await self.get_branch(message.branch_id)
        if parent_branch is None or parent_branch.session_id != session_id:
            raise ConfigError(
                f"message {message_id!s} not in session {session_id!r}",
            )
        prefix = await self._copy_prefix(parent_branch.id, message_id)
        new_branch = await self.create_branch(
            session_id=session_id,
            label=label,
            parent_branch_id=parent_branch.id,
            fork_message_id=message_id,
            activate=activate,
        )
        copied = await self._replicate_prefix(prefix, new_branch.id)
        return new_branch, copied

    async def _copy_prefix(
        self,
        branch_id: UUID,
        through_message_id: UUID,
    ) -> list[ChatMessage]:
        all_messages = await self.list_messages(branch_id)
        prefix: list[ChatMessage] = []
        for msg in all_messages:
            prefix.append(msg)
            if msg.id == through_message_id:
                return prefix
        # Reaching the end without a match means message_id wasn't on
        # this branch — let the caller's null check handle it.
        raise ConfigError(
            f"message {through_message_id!s} not in branch {branch_id!s}",
        )

    async def _replicate_prefix(
        self,
        prefix: Sequence[ChatMessage],
        new_branch_id: UUID,
    ) -> list[ChatMessage]:
        copied: list[ChatMessage] = []
        prev_id: UUID | None = None
        for src in prefix:
            replica = await self.append_message(
                branch_id=new_branch_id,
                role=src.role,
                content=src.content,
                parent_message_id=prev_id,
            )
            copied.append(replica)
            prev_id = replica.id
        return copied

    # ── Helpers ───────────────────────────────────────────────────────

    def _require_open(self) -> None:
        if self._conn is None:
            raise ConfigError("BranchStore is closed; call setup() first")

    def _row_to_branch(self, row: Sequence[object]) -> Branch:
        return Branch(
            id=UUID(cast("str", row[0])),
            session_id=cast("str", row[1]),
            parent_branch_id=(UUID(cast("str", row[2])) if row[2] is not None else None),
            fork_message_id=(UUID(cast("str", row[3])) if row[3] is not None else None),
            label=cast("str", row[4]),
            is_active=bool(row[5]),
            created_at=datetime.fromisoformat(cast("str", row[6])),
        )

    def _row_to_message(self, row: Sequence[object]) -> ChatMessage:
        return ChatMessage(
            id=UUID(cast("str", row[0])),
            branch_id=UUID(cast("str", row[1])),
            role=cast("MessageRole", row[2]),
            content=cast("str", row[3]),
            parent_message_id=(UUID(cast("str", row[4])) if row[4] is not None else None),
            created_at=datetime.fromisoformat(cast("str", row[5])),
        )


@contextlib.asynccontextmanager
async def open_branch_store(db_path: Path):  # type: ignore[no-untyped-def]
    """Async context manager for tests + helpers."""
    store = BranchStore(db_path=db_path)
    await store.setup()
    try:
        yield store
    finally:
        await store.teardown()
