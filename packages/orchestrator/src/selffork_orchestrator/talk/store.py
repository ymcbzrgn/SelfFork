"""SQLite-backed conversation + message store for the Talk surface — S1.

Talk (ADR-007 §4 S1) is the operator ↔ Self Jr direct conversation —
separate from the CLI-session chat in :mod:`selffork_orchestrator.chat`.
The store lives in its own SQLite file (the path is supplied by the
caller, conventionally ``~/.selffork/talk/conversations.db``). SQLite is
the right fit for the same reason the chat branch store uses it: many
small upserts plus per-conversation list scans, and it ships in the
stdlib.

Concurrency mirrors
:class:`~selffork_orchestrator.chat.branch_store.BranchStore`: a single
:class:`asyncio.Lock` serialises writes and the shared connection runs
queries on a worker thread via :func:`anyio.to_thread.run_sync`, so the
dashboard event loop never blocks on disk I/O.
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

from selffork_orchestrator.talk.models import (
    Conversation,
    TalkMessage,
    TalkRole,
)
from selffork_shared.errors import ConfigError

__all__ = ["TalkStore"]


_CONVERSATIONS_DDL = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    workspace_slug TEXT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_message_at TEXT NOT NULL
);
"""

_MESSAGES_DDL = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (conversation_id, seq),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
"""

_INDICES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_conversations_last_message_at "
    "ON conversations(last_message_at);",
    "CREATE INDEX IF NOT EXISTS idx_conversations_workspace_slug "
    "ON conversations(workspace_slug);",
    "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id "
    "ON messages(conversation_id);",
)


_VALID_ROLES: frozenset[str] = frozenset({"operator", "self_jr"})


class TalkStore:
    """SQLite-backed store for Talk conversations + messages.

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
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_schema(self) -> None:
        assert self._conn is not None  # noqa: S101
        self._conn.execute(_CONVERSATIONS_DDL)
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

    # ── Conversations ─────────────────────────────────────────────────

    async def create_conversation(
        self,
        *,
        workspace_slug: str | None,
        title: str,
    ) -> Conversation:
        """Insert a new conversation.

        ``created_at`` and ``last_message_at`` start equal; the latter
        advances on every :meth:`append_message`.
        """
        if not title.strip():
            raise ConfigError("conversation title cannot be empty")
        now = datetime.now(UTC)
        conversation = Conversation(
            id=uuid4(),
            workspace_slug=workspace_slug,
            title=title,
            created_at=now,
            last_message_at=now,
        )
        async with self._lock:
            self._require_open()
            await anyio.to_thread.run_sync(
                self._insert_conversation, conversation
            )
        return conversation

    def _insert_conversation(self, conversation: Conversation) -> None:
        assert self._conn is not None  # noqa: S101
        try:
            self._conn.execute(
                "INSERT INTO conversations "
                "(id, workspace_slug, title, created_at, last_message_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(conversation.id),
                    conversation.workspace_slug,
                    conversation.title,
                    conversation.created_at.isoformat(),
                    conversation.last_message_at.isoformat(),
                ),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    async def get_last_active_workspace(self) -> str | None:
        """Resolve the workspace slug of the most-recently-touched conversation.

        Used by the Telegram inbound router (ADR-006 §4.7.3) to decide
        where to inject a plain-text operator message. Returns ``None``
        when no conversation has ever been bound to a workspace — the
        caller then drops the message into the Telegram drafts queue.

        S3 audit fix #5: filter ``workspace_slug IS NOT NULL`` directly
        so a year-old pinned conversation never wins over a fresh
        orphan — the answer reflects the most-recent *pinned* exchange,
        not any conversation that happens to have a slug.
        """
        async with self._lock:
            self._require_open()
            row = await anyio.to_thread.run_sync(
                self._last_active_workspace_row
            )
        if row is None:
            return None
        slug = row[0]
        return slug if isinstance(slug, str) else None

    def _last_active_workspace_row(self) -> tuple[object, ...] | None:
        assert self._conn is not None  # noqa: S101
        return cast(
            "tuple[object, ...] | None",
            self._conn.execute(
                "SELECT workspace_slug FROM conversations "
                "WHERE workspace_slug IS NOT NULL "
                "ORDER BY last_message_at DESC "
                "LIMIT 1"
            ).fetchone(),
        )

    async def list_conversations(self) -> list[Conversation]:
        """Return every conversation, most-recently-active first."""
        async with self._lock:
            self._require_open()
            rows = await anyio.to_thread.run_sync(
                self._list_conversation_rows
            )
        return [self._row_to_conversation(r) for r in rows]

    def _list_conversation_rows(self) -> list[tuple[object, ...]]:
        assert self._conn is not None  # noqa: S101
        cur = self._conn.execute(
            "SELECT id, workspace_slug, title, created_at, last_message_at "
            "FROM conversations ORDER BY last_message_at DESC"
        )
        return cast("list[tuple[object, ...]]", cur.fetchall())

    async def get_conversation(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        async with self._lock:
            self._require_open()
            row = await anyio.to_thread.run_sync(
                self._fetch_conversation, conversation_id
            )
        return self._row_to_conversation(row) if row is not None else None

    def _fetch_conversation(
        self,
        conversation_id: UUID,
    ) -> tuple[object, ...] | None:
        assert self._conn is not None  # noqa: S101
        cur = self._conn.execute(
            "SELECT id, workspace_slug, title, created_at, last_message_at "
            "FROM conversations WHERE id = ?",
            (str(conversation_id),),
        )
        return cast("tuple[object, ...] | None", cur.fetchone())

    # ── Messages ──────────────────────────────────────────────────────

    async def append_message(
        self,
        *,
        conversation_id: UUID,
        role: TalkRole,
        content: str,
    ) -> TalkMessage:
        """Append a message and advance the conversation's activity clock.

        Assigns the next per-conversation ``seq`` and bumps
        ``conversations.last_message_at`` in the same transaction. Raises
        :class:`ConfigError` for an empty/invalid message or an unknown
        ``conversation_id``.
        """
        if role not in _VALID_ROLES:
            raise ConfigError(f"invalid role {role!r}")
        if not content.strip():
            raise ConfigError("message content cannot be empty")
        message_id = uuid4()
        created_at = datetime.now(UTC)
        async with self._lock:
            self._require_open()
            seq = await anyio.to_thread.run_sync(
                self._insert_message,
                conversation_id,
                message_id,
                role,
                content,
                created_at,
            )
        if seq is None:
            raise ConfigError(
                f"conversation {conversation_id!s} not found",
            )
        return TalkMessage(
            id=message_id,
            conversation_id=conversation_id,
            seq=seq,
            role=role,
            content=content,
            created_at=created_at,
        )

    def _insert_message(
        self,
        conversation_id: UUID,
        message_id: UUID,
        role: TalkRole,
        content: str,
        created_at: datetime,
    ) -> int | None:
        """Insert a message in one transaction and return its ``seq``.

        Returns ``None`` when ``conversation_id`` is unknown so the caller
        can raise a clean :class:`ConfigError`.
        """
        assert self._conn is not None  # noqa: S101
        cur = self._conn.cursor()
        try:
            exists = cur.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (str(conversation_id),),
            ).fetchone()
            if exists is None:
                self._conn.rollback()
                return None
            next_seq = cast(
                "int",
                cur.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM messages "
                    "WHERE conversation_id = ?",
                    (str(conversation_id),),
                ).fetchone()[0],
            )
            cur.execute(
                "INSERT INTO messages "
                "(id, conversation_id, seq, role, content, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(message_id),
                    str(conversation_id),
                    next_seq,
                    role,
                    content,
                    created_at.isoformat(),
                ),
            )
            cur.execute(
                "UPDATE conversations SET last_message_at = ? WHERE id = ?",
                (created_at.isoformat(), str(conversation_id)),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return next_seq

    async def list_messages(
        self,
        conversation_id: UUID,
        *,
        limit: int | None = None,
    ) -> list[TalkMessage]:
        """Return a conversation's messages in ``seq`` order (oldest first)."""
        async with self._lock:
            self._require_open()
            rows = await anyio.to_thread.run_sync(
                self._list_message_rows, conversation_id, limit
            )
        return [self._row_to_message(r) for r in rows]

    def _list_message_rows(
        self,
        conversation_id: UUID,
        limit: int | None,
    ) -> list[tuple[object, ...]]:
        assert self._conn is not None  # noqa: S101
        sql = (
            "SELECT id, conversation_id, seq, role, content, created_at "
            "FROM messages WHERE conversation_id = ? ORDER BY seq ASC"
        )
        params: tuple[object, ...] = (str(conversation_id),)
        if limit is not None:
            sql += " LIMIT ?"
            params = (str(conversation_id), limit)
        return cast(
            "list[tuple[object, ...]]",
            self._conn.execute(sql, params).fetchall(),
        )

    async def list_messages_after(
        self,
        conversation_id: UUID,
        *,
        after_seq: int,
        limit: int = 1000,
    ) -> list[TalkMessage]:
        """Return messages with ``seq > after_seq`` — the WS delta query.

        ``after_seq=0`` returns the whole thread. The ``limit`` cap keeps a
        single WS poll bounded; typical deltas are 1-2 messages.
        """
        async with self._lock:
            self._require_open()
            rows = await anyio.to_thread.run_sync(
                self._list_messages_after_rows,
                conversation_id,
                after_seq,
                limit,
            )
        return [self._row_to_message(r) for r in rows]

    def _list_messages_after_rows(
        self,
        conversation_id: UUID,
        after_seq: int,
        limit: int,
    ) -> list[tuple[object, ...]]:
        assert self._conn is not None  # noqa: S101
        cur = self._conn.execute(
            "SELECT id, conversation_id, seq, role, content, created_at "
            "FROM messages WHERE conversation_id = ? AND seq > ? "
            "ORDER BY seq ASC LIMIT ?",
            (str(conversation_id), after_seq, limit),
        )
        return cast("list[tuple[object, ...]]", cur.fetchall())

    # ── Helpers ───────────────────────────────────────────────────────

    def _require_open(self) -> None:
        if self._conn is None:
            raise ConfigError("TalkStore is closed; call setup() first")

    def _row_to_conversation(self, row: Sequence[object]) -> Conversation:
        return Conversation(
            id=UUID(cast("str", row[0])),
            workspace_slug=cast("str | None", row[1]),
            title=cast("str", row[2]),
            created_at=datetime.fromisoformat(cast("str", row[3])),
            last_message_at=datetime.fromisoformat(cast("str", row[4])),
        )

    def _row_to_message(self, row: Sequence[object]) -> TalkMessage:
        return TalkMessage(
            id=UUID(cast("str", row[0])),
            conversation_id=UUID(cast("str", row[1])),
            seq=cast("int", row[2]),
            role=cast("TalkRole", row[3]),
            content=cast("str", row[4]),
            created_at=datetime.fromisoformat(cast("str", row[5])),
        )


@contextlib.asynccontextmanager
async def open_talk_store(db_path: Path):  # type: ignore[no-untyped-def]
    """Async context manager for tests + helpers."""
    store = TalkStore(db_path=db_path)
    await store.setup()
    try:
        yield store
    finally:
        await store.teardown()
