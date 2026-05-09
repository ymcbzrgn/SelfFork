"""Persistent pending-message inbox for Telegram.

When SelfFork is in ``sleep_until`` (quota cooldown) and the operator types
a message in Telegram, the bridge writes it here. On resume, the round-loop
driver drains the inbox via :meth:`TelegramInbox.list_pending` and prepends
the text to Jr's next user-role message; messages are then marked
delivered via :meth:`TelegramInbox.mark_delivered` so they don't replay
on a future resume.

SQLite over JSONL: the ``WHERE delivered = 0`` predicate is awkward in
append-only files, and the orchestrator already uses SQLite (Mind T2,
project store).
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "PendingMessage",
    "TelegramInbox",
    "default_inbox_path",
]


def default_inbox_path() -> Path:
    """Canonical inbox path: ``~/.selffork/telegram-inbox.sqlite``."""
    return Path.home() / ".selffork" / "telegram-inbox.sqlite"


@dataclass(frozen=True, slots=True)
class PendingMessage:
    """One queued operator message."""

    id: int
    chat_id: int
    text: str
    received_at: datetime
    delivered: bool


class TelegramInbox:
    """SQLite-backed pending-message inbox for ``sleep_until`` recovery."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or default_inbox_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA_SQL)

    @property
    def path(self) -> Path:
        return self._path

    def add(self, *, chat_id: int, text: str) -> PendingMessage:
        """Append a new pending message; returns the persisted record."""
        received_at = datetime.now(tz=UTC)
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "INSERT INTO pending_messages (chat_id, text, received_at, delivered) "
                "VALUES (?, ?, ?, 0)",
                (chat_id, text, received_at.isoformat()),
            )
            conn.commit()
            mid = int(cur.lastrowid or 0)
        return PendingMessage(
            id=mid,
            chat_id=chat_id,
            text=text,
            received_at=received_at,
            delivered=False,
        )

    def list_pending(self) -> list[PendingMessage]:
        """All undelivered messages in receipt order."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, chat_id, text, received_at, delivered "
                "FROM pending_messages WHERE delivered = 0 ORDER BY id ASC",
            ).fetchall()
        return [_row_to_message(r) for r in rows]

    def mark_delivered(self, ids: Iterable[int]) -> int:
        """Mark messages as delivered. Returns affected row count."""
        ids_tuple = tuple(int(i) for i in ids)
        if not ids_tuple:
            return 0
        placeholders = ",".join("?" for _ in ids_tuple)
        with closing(self._connect()) as conn:
            cur = conn.execute(
                f"UPDATE pending_messages SET delivered = 1 "  # noqa: S608 — placeholders fixed
                f"WHERE id IN ({placeholders})",
                ids_tuple,
            )
            conn.commit()
            return cur.rowcount

    def clear(self) -> None:
        """Wipe the inbox. For tests + operator-issued ``/cancel`` flows."""
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM pending_messages")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        return conn


def _row_to_message(row: sqlite3.Row) -> PendingMessage:
    return PendingMessage(
        id=int(row["id"]),
        chat_id=int(row["chat_id"]),
        text=str(row["text"]),
        received_at=datetime.fromisoformat(str(row["received_at"])),
        delivered=bool(row["delivered"]),
    )


_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS pending_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    received_at TEXT NOT NULL,
    delivered INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pending_messages_delivered
    ON pending_messages (delivered, id);
"""
