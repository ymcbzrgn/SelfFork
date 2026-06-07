"""Gemini CLI Snapper — telemetry log + (deferred) /stats child invoke.

Two channels (Order 1 implements channel A; channel B is deferred to a
follow-up patch within Order 1):

A. ``~/.gemini/telemetry.log`` — OTel local-target append-only LogRecords.
   Requires ``telemetry: {target: "local"}`` in ``~/.gemini/settings.json``.
   Each ``gemini_cli.api_response`` LogRecord carries token totals
   (``input_token_count``, ``output_token_count``, ``cached_content_token_count``,
   ``thoughts_token_count``, ``tool_token_count``, ``total_token_count``).

B. ``gemini -p "/stats model" --output-format json`` — OAuth Code Assist
   tier ``retrieveUserQuota`` returns ``BucketInfo[]`` with
   ``remainingFraction`` and ``resetTime``. The headless JSON's ``stats``
   block does NOT carry quota; only the slash command does. Wiring this
   requires a child subprocess with timeout / lock-coordination — deferred.

Auth-only: if ``~/.gemini/oauth_creds.json`` is missing, we return ``None``.

Telemetry OFF (Yamaç's current setup as of 2026-05-09): snapshot returns
``None`` until the user adds ``telemetry.target=local``. The audit-log
derivation layer (``project_provider_usage_source``) acts as the fallback.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from selffork_orchestrator.snappers.base import Snapper
from selffork_shared.quota import ContextState, QuotaSnapshot, WindowKind, WindowState

__all__ = ["GeminiSnapper"]

_DEFAULT_GEMINI_DIR = Path.home() / ".gemini"

# Conservative working default: Gemini 2.5 Pro is 1M; Flash variants are
# 128k/1M depending on tier. The audit-log layer carries the precise
# per-model window; the snapper provides a coarse approximation suitable
# for the autopilot's `compact_context` early-warning trigger.
_DEFAULT_GEMINI_CONTEXT_WINDOW = 1_000_000


class GeminiSnapper(Snapper):
    """Telemetry log tail → :class:`QuotaSnapshot` (context only for now).

    Args:
        gemini_home: Override config dir (default ``~/.gemini``).
        telemetry_path: Override telemetry log path (default
            ``~/.gemini/telemetry.log``).
        max_tail_bytes: Maximum bytes to read from end of telemetry log.
        context_window: Override context-window approximation (default 1M).
    """

    def __init__(
        self,
        gemini_home: Path | None = None,
        telemetry_path: Path | None = None,
        *,
        max_tail_bytes: int = 65536,
        context_window: int = _DEFAULT_GEMINI_CONTEXT_WINDOW,
    ) -> None:
        super().__init__(cli_id="gemini-cli")
        self._gemini_home = gemini_home if gemini_home is not None else _DEFAULT_GEMINI_DIR
        self._telemetry_path = (
            telemetry_path if telemetry_path is not None else self._gemini_home / "telemetry.log"
        )
        self._max_tail_bytes = max(max_tail_bytes, 1024)
        self._context_window = max(context_window, 1)

    async def snapshot(self) -> QuotaSnapshot | None:
        if not (self._gemini_home / "oauth_creds.json").exists():
            return None
        if not self._telemetry_path.exists():
            return None
        try:
            tail = self._tail_text(self._telemetry_path, self._max_tail_bytes)
        except OSError:
            return None
        context = self._derive_context(tail, self._context_window)
        windows: dict[WindowKind, WindowState] = {}  # /stats child invoke deferred
        return QuotaSnapshot(
            cli_id="gemini-cli",
            account_id=None,
            windows=windows,
            context=context,
            captured_at=datetime.now(tz=UTC),
            source="telemetry.log",
        )

    @staticmethod
    def _tail_text(path: Path, max_bytes: int) -> str:
        size = path.stat().st_size
        offset = max(size - max_bytes, 0)
        with path.open("rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
        return chunk.decode("utf-8", errors="replace")

    @staticmethod
    def _derive_context(tail: str, window: int) -> ContextState | None:
        # OTel target=local writes one JSON LogRecord per line.
        # Find the most recent api_response record and use its token totals.
        for raw_line in reversed(tail.splitlines()):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            attrs = obj.get("attributes")
            if not isinstance(attrs, dict):
                continue
            event_marker = obj.get("body") or attrs.get("event.name") or obj.get("name") or ""
            if not isinstance(event_marker, str) or "api_response" not in event_marker:
                continue
            total = attrs.get("total_token_count")
            if not isinstance(total, int) or total <= 0:
                continue
            used_pct = min((total * 100.0) / window, 100.0)
            return ContextState(
                used_tokens=total,
                total_tokens=window,
                used_pct=used_pct,
            )
        return None
