"""Z.AI / GLM Coding Plan snapper.

ARGE 2026-05-09: Yamaç's Z.AI subscription is routed through
``opencode auth login`` (native OAuth). The OAuth token lives in
opencode's auth.json under the ``zai`` provider key (``providers.zai.access``).

This snapper confirms login state and emits an empty-windows snapshot
sourced from the opencode auth file. The full HTTP probe to
``api.z.ai/v1/usage`` (community plugin pattern from
``dcristob/zai_usage_opencode``) lands in a follow-up patch.

Auth-only kuralı: Yamaç ASLA API key kullanmaz. We deliberately reject
``providers.zai`` entries that aren't ``type: "oauth"``.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from selffork_orchestrator.snappers.base import Snapper
from selffork_shared.quota import QuotaSnapshot

__all__ = ["ZaiSnapper", "default_opencode_auth_path"]


def default_opencode_auth_path() -> Path:
    """Resolve opencode's auth.json (macOS / Linux fallback).

    On macOS opencode writes to ``~/Library/Application Support/opencode/auth.json``;
    Linux falls back to ``~/.local/share/opencode/auth.json``. Snapper picks
    whichever exists at call time so the same code works on both.
    """
    macos_path = (
        Path.home()
        / "Library"
        / "Application Support"
        / "opencode"
        / "auth.json"
    )
    if macos_path.exists():
        return macos_path
    return Path.home() / ".local" / "share" / "opencode" / "auth.json"


class ZaiSnapper(Snapper):
    """Z.AI subscription snapper.

    Args:
        opencode_auth_path: Override (default resolves macOS / Linux paths).
    """

    def __init__(self, opencode_auth_path: Path | None = None) -> None:
        super().__init__(cli_id="zai")
        self._auth_path = (
            opencode_auth_path
            if opencode_auth_path is not None
            else default_opencode_auth_path()
        )

    async def snapshot(self) -> QuotaSnapshot | None:
        if not self._auth_path.exists():
            return None
        try:
            text = self._auth_path.read_text(encoding="utf-8")
            data = json.loads(text)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        providers = data.get("providers")
        if not isinstance(providers, dict):
            return None
        zai = providers.get("zai")
        if not isinstance(zai, dict):
            return None
        # Auth-only: reject API-key entries (auth-only kural).
        if zai.get("type") != "oauth":
            return None
        if not zai.get("access"):
            return None
        return QuotaSnapshot(
            cli_id="zai",
            account_id=None,
            windows={},  # /v1/usage HTTP probe deferred to follow-up patch
            context=None,
            captured_at=datetime.now(tz=UTC),
            source="opencode-auth-zai",
        )
