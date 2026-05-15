"""Claude Code Snapper — raw statusline JSON → normalized QuotaSnapshot.

The bash side (``claude_snap.sh``) is invoked by Claude Code's
``~/.claude/statusline.sh`` (one-time manual setup) and writes the raw
stdin JSON to ``~/.selffork/cli-state/raw/claude.json``.

This Python snapper parses that raw file. The schema we read matches
Claude Code v2.1.80+ statusline contract (verified at
https://code.claude.com/docs/en/statusline):

  rate_limits.five_hour.{used_percentage, resets_at}    int epoch sec
  rate_limits.seven_day.{used_percentage, resets_at}    int epoch sec
  context_window.context_window_size                    int (200000 or 1000000)
  context_window.used_percentage                        float 0-100, may be null
  context_window.current_usage.{input_tokens, output_tokens,
                                cache_creation_input_tokens,
                                cache_read_input_tokens}
  model.{display_name, id}
  session_id

``rate_limits`` is **only** present on Pro/Max subscriptions and only after
the first API call of the session. API-key-auth and pre-first-API sessions
yield empty ``windows`` but populated ``context``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from selffork_orchestrator.snappers.base import Snapper
from selffork_shared.quota import (
    ContextState,
    QuotaSnapshot,
    WindowKind,
    WindowState,
)

__all__ = ["ClaudeSnapper", "default_raw_path"]

_FIVE_HOUR_SECONDS = 5 * 3600
_SEVEN_DAY_SECONDS = 7 * 24 * 3600


def default_raw_path() -> Path:
    """Default path the bash snap script writes raw stdin JSON to."""
    return Path.home() / ".selffork" / "cli-state" / "raw" / "claude.json"


class ClaudeSnapper(Snapper):
    """Project Claude Code's statusline JSON push into a :class:`QuotaSnapshot`.

    Pull-mode: the bash side does the stdin → file capture. We just read
    the latest raw file each tick and normalize.
    """

    def __init__(self, raw_path: Path | None = None) -> None:
        super().__init__(cli_id="claude-code")
        self._raw_path = raw_path if raw_path is not None else default_raw_path()

    async def snapshot(self) -> QuotaSnapshot | None:
        if not self._raw_path.exists():
            return None
        try:
            text = self._raw_path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Bash side wrote partially in the middle of a tee; SnapperRunner
            # re-invokes us next tick.
            return None
        if not isinstance(data, dict):
            return None

        windows = self._parse_windows(data.get("rate_limits") or {})
        context = self._parse_context(data.get("context_window") or {})
        return QuotaSnapshot(
            cli_id="claude-code",
            account_id=None,
            windows=windows,
            context=context,
            captured_at=datetime.now(tz=UTC),
            source="statusline.sh",
        )

    @staticmethod
    def _parse_windows(rate_limits: dict[str, object]) -> dict[WindowKind, WindowState]:
        windows: dict[WindowKind, WindowState] = {}
        for source_key, window_seconds, target in (
            ("five_hour", _FIVE_HOUR_SECONDS, WindowKind.five_hour),
            ("seven_day", _SEVEN_DAY_SECONDS, WindowKind.seven_day),
        ):
            window_data = rate_limits.get(source_key)
            if not isinstance(window_data, dict):
                continue
            used_pct = window_data.get("used_percentage")
            resets_at_epoch = window_data.get("resets_at")
            if not isinstance(used_pct, (int, float)):
                continue
            if not isinstance(resets_at_epoch, (int, float)):
                continue
            try:
                resets_at = datetime.fromtimestamp(int(resets_at_epoch), tz=UTC)
            except (OSError, ValueError, OverflowError):
                continue
            windows[target] = WindowState(
                used_pct=float(used_pct),
                resets_at=resets_at,
                window_seconds=window_seconds,
            )
        return windows

    @staticmethod
    def _parse_context(context_window: dict[str, object]) -> ContextState | None:
        size = context_window.get("context_window_size")
        if not isinstance(size, int) or size <= 0:
            return None
        current = context_window.get("current_usage")
        used = 0
        if isinstance(current, dict):
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            ):
                value = current.get(key)
                if isinstance(value, int):
                    used += max(value, 0)
        if used == 0:
            # Pre-first-API: try used_percentage fallback.
            pct = context_window.get("used_percentage")
            if isinstance(pct, (int, float)) and float(pct) > 0.0:
                used = round(size * float(pct) / 100.0)
        used_pct = (used * 100.0) / size
        return ContextState(
            used_tokens=used,
            total_tokens=size,
            used_pct=used_pct,
        )
