"""Telegram operator allowlist.

Single-user today (Yamaç only); multi-operator forward-compat (multiple
chat_ids supported). JSON format at ``~/.selffork/operators.json``::

    {
      "chat_ids": [12345678, 87654321],
      "default_project_slug": "demo"
    }

Loader is fail-safe: missing file, invalid JSON, or wrong shape all
collapse to an empty allowlist (which rejects every chat_id).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "AllowList",
    "AllowListConfig",
    "default_allowlist_path",
]


def default_allowlist_path() -> Path:
    """Canonical allowlist path: ``~/.selffork/operators.json``."""
    return Path.home() / ".selffork" / "operators.json"


@dataclass(frozen=True, slots=True)
class AllowListConfig:
    """Loader configuration."""

    path: Path | None = None  # defaults to ``default_allowlist_path()``


@dataclass(frozen=True, slots=True)
class AllowList:
    """In-memory allowlist for inbound Telegram chats."""

    chat_ids: frozenset[int] = field(default_factory=frozenset)
    default_project_slug: str | None = None

    def is_allowed(self, chat_id: int) -> bool:
        """True when ``chat_id`` is permitted to interact with SelfFork."""
        return chat_id in self.chat_ids

    @classmethod
    def load(cls, config: AllowListConfig | None = None) -> AllowList:
        """Load + validate the allowlist file.

        Returns an empty allowlist for any failure mode (file missing,
        unreadable, invalid JSON, wrong shape). The caller is expected
        to surface a clear error to the operator if the empty list is
        unexpected — we never raise from here.
        """
        path = (config.path if config else None) or default_allowlist_path()
        if not path.exists():
            return cls()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return cls()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return cls()
        if not isinstance(data, dict):
            return cls()
        ids_raw = data.get("chat_ids")
        ids: list[int] = []
        if isinstance(ids_raw, list):
            for x in ids_raw:
                if isinstance(x, int) and not isinstance(x, bool):
                    ids.append(x)
        slug = data.get("default_project_slug")
        return cls(
            chat_ids=frozenset(ids),
            default_project_slug=slug if isinstance(slug, str) else None,
        )
