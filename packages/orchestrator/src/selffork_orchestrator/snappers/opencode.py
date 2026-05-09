"""OpenCode Snapper — SQLite poll → QuotaSnapshot (context only).

OpenCode v3 stores all session/message state in an embedded SQLite database.
On macOS the canonical path is
``~/Library/Application Support/opencode/opencode.db``; on Linux it falls
back to ``~/.local/share/opencode/opencode.db``.

Schema (verified via DeepWiki + ``packages/opencode/src/session/session.sql.ts``):

    CREATE TABLE message (
      id TEXT PRIMARY KEY,
      session_id TEXT REFERENCES session(id) ON DELETE CASCADE,
      time_created INTEGER,
      time_updated INTEGER,
      data TEXT  -- JSON Zod-serialized Message{User|Assistant}
    );

The Assistant message JSON includes::

    {
      "role": "assistant",
      "modelID": "...", "providerID": "...",
      "cost": 0.0123,
      "tokens": {
        "input": 1234, "output": 567, "reasoning": 0,
        "cache": {"read": 9876, "write": 0},
        "total": 11760
      },
      ...
    }

OpenCode does NOT expose subscription rate-limit headers (provider 429s
surface as ``AssistantError`` only — see ``session/retry.ts``). This
snapper therefore only fills :class:`ContextState`; ``windows`` stays
empty and the autopilot relies on the audit-log derivation layer for
per-provider quota.

WAL mode allows concurrent reads while OpenCode writes — we open with
``mode=ro`` for read-only safety.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from selffork_orchestrator.snappers.base import Snapper
from selffork_shared.quota import ContextState, QuotaSnapshot

__all__ = ["OpenCodeSnapper", "default_opencode_db_path"]

# Conservative default; Anthropic 200k is the most common ceiling for
# subscription routes. The audit-log layer carries the model-specific
# window; this is approximation for the autopilot's compact_context guard.
_DEFAULT_OPENCODE_CONTEXT_WINDOW = 200_000


def default_opencode_db_path() -> Path:
    """Resolve the opencode SQLite db path for the current platform.

    Picks the macOS path if it exists, otherwise the Linux XDG default.
    """
    macos_path = (
        Path.home() / "Library" / "Application Support" / "opencode" / "opencode.db"
    )
    if macos_path.exists():
        return macos_path
    return Path.home() / ".local" / "share" / "opencode" / "opencode.db"


class OpenCodeSnapper(Snapper):
    """Tail opencode SQLite → :class:`QuotaSnapshot` (ContextState only)."""

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        context_window: int = _DEFAULT_OPENCODE_CONTEXT_WINDOW,
    ) -> None:
        super().__init__(cli_id="opencode")
        self._db_path = db_path if db_path is not None else default_opencode_db_path()
        self._context_window = max(context_window, 1)

    async def snapshot(self) -> QuotaSnapshot | None:
        if not self._db_path.exists():
            return None
        try:
            row = self._latest_assistant_data()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        try:
            data = json.loads(row)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        context = self._parse_context(data, self._context_window)
        return QuotaSnapshot(
            cli_id="opencode",
            account_id=None,
            windows={},
            context=context,
            captured_at=datetime.now(tz=UTC),
            source="sqlite-poll",
        )

    def _latest_assistant_data(self) -> str | None:
        # Read-only URI keeps us out of WAL writer's way. timeout=2.0 is a
        # generous bound; opencode SQLite ops are sub-millisecond.
        uri = f"file:{self._db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        try:
            cur = conn.execute(
                "SELECT data FROM message ORDER BY time_created DESC, id DESC LIMIT 1",
            )
            row = cur.fetchone()
            return str(row[0]) if row and row[0] is not None else None
        finally:
            conn.close()

    @staticmethod
    def _parse_context(message: dict[str, object], window: int) -> ContextState | None:
        if message.get("role") != "assistant":
            return None
        tokens = message.get("tokens")
        if not isinstance(tokens, dict):
            return None
        used = 0
        for key in ("input", "output", "reasoning"):
            value = tokens.get(key)
            if isinstance(value, int):
                used += max(value, 0)
        cache = tokens.get("cache")
        if isinstance(cache, dict):
            for key in ("read", "write"):
                value = cache.get(key)
                if isinstance(value, int):
                    used += max(value, 0)
        if used == 0:
            return None
        used_pct = min((used * 100.0) / window, 100.0)
        return ContextState(
            used_tokens=used,
            total_tokens=window,
            used_pct=used_pct,
        )
