"""Telegram draft queue — operator messages with no active workspace.

When the operator sends a plain-text message via Telegram and SelfFork
has no active workspace to attach it to (the last Talk conversation is
stale, no project has been resolved, etc.), the inbound router drops
the message into this queue. The Talk page renders a banner
("📲 N message(s) from Telegram") so the operator can review the
backlog when they next open the cockpit.

This is a separate concern from :class:`TelegramInbox`: the inbox
buffers messages received while the round-loop is in ``sleep_until``
(quota cooldown) so they can be replayed to Self Jr on resume.
Drafts target the **Talk** surface, not the round-loop.

SQLite at ``~/.selffork/telegram-drafts.sqlite``; the schema mirrors
the inbox closely so the storage layer stays cheap to maintain.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "TelegramDraft",
    "TelegramDraftStore",
    "default_drafts_path",
]


def default_drafts_path() -> Path:
    """Canonical drafts path: ``~/.selffork/telegram-drafts.sqlite``."""
    return Path.home() / ".selffork" / "telegram-drafts.sqlite"


@dataclass(frozen=True, slots=True)
class TelegramDraft:
    """One queued operator draft awaiting a Talk context."""

    id: int
    chat_id: int
    sender: str | None  # operator username if Telegram surfaces it
    text: str
    received_at: datetime
    claimed: bool


class TelegramDraftStore:
    """SQLite-backed drop queue for unrouted Telegram messages."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or default_drafts_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA_SQL)

    @property
    def path(self) -> Path:
        return self._path

    def add(
        self,
        *,
        chat_id: int,
        text: str,
        sender: str | None = None,
    ) -> TelegramDraft:
        """Append a new draft; returns the persisted record."""
        received_at = datetime.now(tz=UTC)
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "INSERT INTO drafts (chat_id, sender, text, received_at, claimed) "
                "VALUES (?, ?, ?, ?, 0)",
                (chat_id, sender, text, received_at.isoformat()),
            )
            conn.commit()
            did = int(cur.lastrowid or 0)
        return TelegramDraft(
            id=did,
            chat_id=chat_id,
            sender=sender,
            text=text,
            received_at=received_at,
            claimed=False,
        )

    def list_unclaimed(self) -> list[TelegramDraft]:
        """Return all unclaimed drafts in receipt order."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, chat_id, sender, text, received_at, claimed "
                "FROM drafts WHERE claimed = 0 ORDER BY id ASC",
            ).fetchall()
        return [_row_to_draft(r) for r in rows]

    def count_unclaimed(self) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM drafts WHERE claimed = 0"
            ).fetchone()
        return int(row[0]) if row else 0

    def claim(self, ids: Iterable[int]) -> int:
        """Mark drafts as claimed (acknowledged by the operator)."""
        ids_tuple = tuple(int(i) for i in ids)
        if not ids_tuple:
            return 0
        placeholders = ",".join("?" for _ in ids_tuple)
        with closing(self._connect()) as conn:
            cur = conn.execute(
                f"UPDATE drafts SET claimed = 1 "  # noqa: S608 — placeholders fixed
                f"WHERE id IN ({placeholders})",
                ids_tuple,
            )
            conn.commit()
            return cur.rowcount

    def clear(self) -> None:
        """Wipe all drafts. Test + operator ``/cancel`` flows."""
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM drafts")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        return conn


def _row_to_draft(row: sqlite3.Row) -> TelegramDraft:
    return TelegramDraft(
        id=int(row["id"]),
        chat_id=int(row["chat_id"]),
        sender=row["sender"],
        text=str(row["text"]),
        received_at=datetime.fromisoformat(str(row["received_at"])),
        claimed=bool(row["claimed"]),
    )


_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    sender TEXT,
    text TEXT NOT NULL,
    received_at TEXT NOT NULL,
    claimed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_drafts_claimed
    ON drafts (claimed, id);
"""
