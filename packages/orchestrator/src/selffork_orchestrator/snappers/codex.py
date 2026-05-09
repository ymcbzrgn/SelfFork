"""Codex CLI Snapper — rollout JSONL TokenCountEvent → QuotaSnapshot.

Codex CLI (OpenAI's official, ChatGPT Plus auth) appends a rollout JSONL
file per session at ``~/.codex/sessions/YYYY/MM/DD/rollout-<session_id>.jsonl``.
Each turn appends a ``token_count`` event with a structure approximating::

    {
      "type": "event_msg",
      "payload": {
        "type": "token_count",
        "info": {
          "total_token_usage":
              {"input_tokens": ..., "output_tokens": ..., "reasoning_tokens": ..., ...},
          "model_context_window": ...
        },
        "rate_limits": {
          "primary":   {"used_percent": 23.5, "window_minutes": 300,   "resets_in_seconds": 12345},
          "secondary": {"used_percent": 41.2, "window_minutes": 10079, "resets_in_seconds": 234567}
        }
      },
      "timestamp": "2026-05-09T..."
    }

We tail the latest-mtime ``rollout-*.jsonl`` under today's directory (and
yesterday's, to cover the UTC midnight rollover) and emit a snapshot from
the most recent ``token_count`` event.

Auth-only: if ``~/.codex/auth.json`` is missing, we return ``None``.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from selffork_orchestrator.snappers.base import Snapper
from selffork_shared.quota import (
    ContextState,
    QuotaSnapshot,
    WindowKind,
    WindowState,
)

__all__ = ["CodexSnapper"]


def _default_codex_dir() -> Path:
    return Path.home() / ".codex"


class CodexSnapper(Snapper):
    """Tail Codex rollout JSONL → :class:`QuotaSnapshot`.

    Args:
        codex_home: Override config dir (default ``~/.codex``).
        scan_days: Days back from today to consider when finding the
            latest rollout (default 2 — covers UTC-midnight rollover).
    """

    def __init__(
        self,
        codex_home: Path | None = None,
        *,
        scan_days: int = 2,
    ) -> None:
        super().__init__(cli_id="codex")
        self._codex_home = codex_home if codex_home is not None else _default_codex_dir()
        self._scan_days = max(scan_days, 1)

    async def snapshot(self) -> QuotaSnapshot | None:
        if not (self._codex_home / "auth.json").exists():
            return None
        rollout = self._latest_rollout()
        if rollout is None:
            return None
        event = self._latest_token_count_event(rollout)
        if event is None:
            return None
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return None
        captured_at = self._parse_event_timestamp(event) or datetime.now(tz=UTC)
        windows = self._parse_windows(payload.get("rate_limits"), captured_at=captured_at)
        context = self._parse_context(payload.get("info"))
        return QuotaSnapshot(
            cli_id="codex",
            account_id=None,
            windows=windows,
            context=context,
            captured_at=captured_at,
            source=f"rollout-jsonl:{rollout.name}",
        )

    def _candidate_dirs(self) -> list[Path]:
        sessions_dir = self._codex_home / "sessions"
        if not sessions_dir.is_dir():
            return []
        today = datetime.now(tz=UTC).date()
        candidates: list[Path] = []
        for offset in range(self._scan_days):
            day = today - timedelta(days=offset)
            candidates.append(
                sessions_dir / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}",
            )
        return [p for p in candidates if p.is_dir()]

    def _latest_rollout(self) -> Path | None:
        latest: tuple[float, Path] | None = None
        for d in self._candidate_dirs():
            for p in d.glob("rollout-*.jsonl"):
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    continue
                if latest is None or mtime > latest[0]:
                    latest = (mtime, p)
        return latest[1] if latest else None

    @staticmethod
    def _latest_token_count_event(path: Path) -> dict[str, object] | None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        # Walk from the end backward; first matching token_count wins.
        for raw_line in reversed(text.splitlines()):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("type") == "token_count":
                return obj
        return None

    @staticmethod
    def _parse_event_timestamp(event: dict[str, object]) -> datetime | None:
        ts = event.get("timestamp")
        if not isinstance(ts, str):
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _parse_windows(
        rate_limits: object,
        *,
        captured_at: datetime,
    ) -> dict[WindowKind, WindowState]:
        if not isinstance(rate_limits, dict):
            return {}
        result: dict[WindowKind, WindowState] = {}
        for source_key, target in (
            ("primary", WindowKind.five_hour),
            ("secondary", WindowKind.seven_day),
        ):
            window_data = rate_limits.get(source_key)
            if not isinstance(window_data, dict):
                continue
            used_pct = window_data.get("used_percent")
            resets_in = window_data.get("resets_in_seconds")
            window_minutes = window_data.get("window_minutes")
            if not isinstance(used_pct, (int, float)):
                continue
            if not isinstance(resets_in, (int, float)):
                continue
            try:
                resets_at = captured_at + timedelta(seconds=int(resets_in))
            except OverflowError:
                continue
            window_seconds = (
                max(int(window_minutes) * 60, 1)
                if isinstance(window_minutes, (int, float))
                else 1
            )
            result[target] = WindowState(
                used_pct=float(used_pct),
                resets_at=resets_at,
                window_seconds=window_seconds,
            )
        return result

    @staticmethod
    def _parse_context(info: object) -> ContextState | None:
        if not isinstance(info, dict):
            return None
        ctx = info.get("model_context_window")
        if not isinstance(ctx, int) or ctx <= 0:
            return None
        usage = info.get("total_token_usage")
        if not isinstance(usage, dict):
            return None
        used = 0
        # Codex rollout JSONL field naming has historically used both
        # ``cached_input_tokens`` and ``cached_tokens``. Avoid double-count
        # by giving ``cached_input_tokens`` precedence; only fall back to
        # ``cached_tokens`` when the former is absent.
        for key in ("input_tokens", "output_tokens", "reasoning_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                used += max(value, 0)
        cache_value = usage.get("cached_input_tokens")
        if not isinstance(cache_value, int):
            cache_value = usage.get("cached_tokens")
        if isinstance(cache_value, int):
            used += max(cache_value, 0)
        if used == 0:
            return None
        used_pct = (used * 100.0) / ctx
        return ContextState(
            used_tokens=used,
            total_tokens=ctx,
            used_pct=used_pct,
        )
