"""ClaudeRateLimitDetector — rate-limit + auth detection for ``claude`` CLI.

Two parsing paths (in priority order):

1. **stream-json**: when the CLI was invoked with
   ``--output-format stream-json --verbose``, stdout is newline-delimited
   JSON. Look for events of the form
   ``{"type": "system", "subtype": "api_retry", "error": "rate_limit",
   "error_status": 429, ...}``. The ``error`` field is a documented enum:
   ``rate_limit | authentication_failed | oauth_org_not_allowed |
   billing_error | invalid_request | server_error | max_output_tokens |
   unknown`` (verified by selffork-researcher 2026-05-01).
2. **Text fallback**: when default text mode is used (e.g. ``-p`` alone),
   parse ``"Claude usage limit reached. Your limit will reset at
   <H>(am|pm) (<IANA-tz>)"`` (verbatim from anthropics/claude-code
   issue #5977 + variants in #9236, #1947). Distinguish the transient
   server burst-limiter (``"Server is temporarily limiting requests
   (not your usage limit)"``, #53922) — that's a short retry, NOT a
   subscription-limit pause.

Reset-time format from the text path is 12h wall-clock + IANA timezone
in parens. We parse it with :mod:`zoneinfo` for accurate wall-clock →
UTC conversion.

If neither path resolves, fall back to ``now + 5h`` per Anthropic's
default 5-hour window (so a stuck loop never busy-loops).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from selffork_orchestrator.limits.base import (
    AuthRequired,
    LimitDetector,
    LimitVerdict,
    NoLimit,
    RateLimited,
)

__all__ = ["ClaudeRateLimitDetector"]

# Errors in the stream-json ``error`` enum that map to RateLimited /
# AuthRequired / NoLimit. The "unknown" / "server_error" / "invalid_request"
# / "max_output_tokens" / "billing_error" cases are returned as NoLimit
# from the rate-limit perspective — the caller will still see exit_code != 0
# and surface the failure normally; we only intercept quota and auth.
_RATE_LIMIT_ERRORS: frozenset[str] = frozenset({"rate_limit"})
_AUTH_ERRORS: frozenset[str] = frozenset(
    {"authentication_failed", "oauth_org_not_allowed"},
)

# Subscription-limit text. Group 1 = digit, 2 = am|pm, 3 = IANA timezone.
# ``(?:AI )?`` accommodates both "Claude usage limit reached" and the older
# "Claude AI usage limit reached" variant; both are documented in claude-code
# issue threads.
_TEXT_LIMIT_RE = re.compile(
    r"Claude (?:AI )?usage limit reached.*?reset(?:\s+at)?\s+"
    r"(\d{1,2})\s*(am|pm)\s*\(([^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)

# Server burst-limiter (transient, NOT subscription quota). Short backoff.
_BURST_LIMIT_RE = re.compile(
    r"Server is temporarily limiting requests \(not your usage limit\)",
    re.IGNORECASE,
)

# Auth-failure heuristic for text-mode output. The CLI usually prompts the
# user to re-login; we look for that hint.
_AUTH_TEXT_RE = re.compile(
    r"(please\s+(?:re-?)?login|run\s+`?claude\s+login`?|invalid_api_key|"
    r"authentication\s+(?:failed|required))",
    re.IGNORECASE,
)


class ClaudeRateLimitDetector(LimitDetector):
    """Subscription rate-limit + auth detector for ``claude`` CLI."""

    def detect(
        self,
        *,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> LimitVerdict:
        del exit_code  # Unused: rate-limit is signaled by output, not exit code.

        # Path 1: stream-json (preferred — explicit error enum).
        json_verdict = self._detect_stream_json(stdout)
        if json_verdict is not None:
            return json_verdict

        # Path 2: text-mode regex on stdout + stderr (legacy / -p text mode).
        combined = f"{stdout}\n{stderr}"
        text_verdict = self._detect_text(combined)
        if text_verdict is not None:
            return text_verdict

        return NoLimit()

    # ── stream-json path ──────────────────────────────────────────────────

    @staticmethod
    def _detect_stream_json(stdout: str) -> LimitVerdict | None:
        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("subtype") != "api_retry":
                continue
            err = obj.get("error")
            if not isinstance(err, str):
                continue
            if err in _AUTH_ERRORS:
                return AuthRequired(
                    reason=(
                        f"claude CLI reported {err!r}; run `claude /login` to re-authenticate."
                    ),
                )
            if err in _RATE_LIMIT_ERRORS:
                # stream-json doesn't carry a reset time; fall back to
                # the 5h default per Anthropic Pro/Max semantics. Text
                # path overrides this when present.
                return RateLimited(
                    reset_at=datetime.now(UTC) + timedelta(hours=5),
                    reason="claude stream-json reported error='rate_limit'",
                    kind="unknown",
                )
        return None

    # ── text-mode path ────────────────────────────────────────────────────

    @classmethod
    def _detect_text(cls, text: str) -> LimitVerdict | None:
        if _BURST_LIMIT_RE.search(text):
            # Transient burst-limit: NOT a subscription quota. Treat as
            # NoLimit so the orchestrator's normal error path handles it
            # (typically a short retry). Returning RateLimited here would
            # schedule a multi-hour pause for what is a 30-second issue.
            return NoLimit()

        m = _TEXT_LIMIT_RE.search(text)
        if m is not None:
            hour = int(m.group(1))
            ampm = m.group(2).lower()
            tz_name = m.group(3).strip()
            reset_at = _parse_reset_at(hour=hour, ampm=ampm, tz_name=tz_name)
            return RateLimited(
                reset_at=reset_at,
                reason=(f"claude usage limit reached; reset at {hour}{ampm} {tz_name}"),
                kind="unknown",  # text doesn't disambiguate 5h vs weekly
            )

        if _AUTH_TEXT_RE.search(text):
            return AuthRequired(
                reason=(
                    "claude CLI reports an auth failure; run `claude /login` to re-authenticate."
                ),
            )
        return None


def _parse_reset_at(*, hour: int, ampm: str, tz_name: str) -> datetime:
    """Convert a ``<H>(am|pm) (<IANA-tz>)`` claude reset hint to UTC.

    The CLI reports e.g. ``2pm (America/New_York)``; we resolve that to
    the next future moment matching that wall clock in that timezone,
    then convert to UTC. A tiny safety margin (60s) is added so we
    don't poke the API exactly when the window opens.

    Falls back to ``now + 5h UTC`` when the timezone name doesn't
    resolve (e.g. malformed CLI output).
    """
    now_utc = datetime.now(UTC)
    safety = timedelta(seconds=60)

    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return now_utc + timedelta(hours=5) + safety

    hour24 = hour % 12
    if ampm == "pm":
        hour24 += 12

    now_local = now_utc.astimezone(tz)
    candidate = now_local.replace(hour=hour24, minute=0, second=0, microsecond=0)
    if candidate <= now_local:
        # Reset time is earlier today (or now) → must mean tomorrow.
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC) + safety
