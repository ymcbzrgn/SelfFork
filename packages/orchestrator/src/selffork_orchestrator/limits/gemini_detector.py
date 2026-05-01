"""GeminiRateLimitDetector — rate-limit + auth detection for ``gemini`` CLI.

Per selffork-researcher 2026-05-01: gemini-cli does NOT emit a fatal exit
code on quota (in contrast to auth=41), and ``--output-format json`` is
unreliable in 0.39.x (multiple GitHub issues). So our primary path is
**stderr/stdout regex**.

Three reset-time formats observed across the issue tracker:

1. **RPM (per-minute)** — short retry hint, sub-minute precision::

       Please retry in 15.002899939s

2. **RPD (daily)** — wall-clock with timezone offset::

       Usage limit reached for gemini-3-flash-preview.
       Access resets at 10:57 PM GMT-3.

3. **Embedded retryDelay** in the JSON-ish error body::

       "retryDelay": "30s"

When none of the three are parseable, fall back to **midnight Pacific
(America/Los_Angeles)** + 60s safety, per ai.google.dev's documented
"RPD quotas reset at midnight Pacific time" rule.

Auth is signaled via exit code 41 OR the ``FatalAuthenticationError``
substring (verified by selffork-researcher: troubleshooting docs +
PR #13728).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from selffork_orchestrator.limits.base import (
    AuthRequired,
    LimitDetector,
    LimitVerdict,
    NoLimit,
    RateLimited,
)

__all__ = ["GeminiRateLimitDetector"]

# Documented gemini fatal exit code for auth (PR #13728).
_AUTH_EXIT_CODE = 41

# Quota signal patterns. ``re.IGNORECASE`` for variant casing across
# error messages; verbatim phrases come from issue tracker quotes.
_QUOTA_RE = re.compile(
    r"\b("
    r"429"
    r"|RESOURCE_EXHAUSTED"
    r"|exceeded\s+your\s+current\s+quota"
    r"|Quota\s+exceeded\s+for\s+metric"
    r"|exhausted\s+your\s+daily\s+quota"
    r"|Resource\s+exhausted"
    r"|Usage\s+limit\s+reached"
    r")\b",
    re.IGNORECASE,
)

# Auth heuristic for text mode (we also check exit code).
_AUTH_RE = re.compile(
    r"\b("
    r"FatalAuthenticationError"
    r"|Failed\s+to\s+exchange\s+authorization"
    r"|invalid_grant"
    r"|reauthent"
    r"|Authentication\s+failed"
    r")\b",
    re.IGNORECASE,
)

# RPM format: "Please retry in 15.002899939s" (fractional seconds).
_RPM_RE = re.compile(
    r"Please\s+retry\s+in\s+(\d+(?:\.\d+)?)\s*s\b",
    re.IGNORECASE,
)

# RPD format: "Access resets at 10:57 PM GMT-3" (or "GMT+5:30" rare).
# Group 1 = HH, 2 = MM, 3 = AM/PM, 4 = signed hours, 5 = optional minutes.
_RPD_RE = re.compile(
    r"Access\s+resets\s+at\s+"
    r"(\d{1,2}):(\d{2})\s*(AM|PM)\s*GMT([+-]\d+)(?::(\d{2}))?",
    re.IGNORECASE,
)

# JSON-ish embedded retryDelay: "retryDelay": "30s"
_RETRY_DELAY_RE = re.compile(
    r"retryDelay[\"']?\s*:\s*[\"'](\d+)s[\"']",
    re.IGNORECASE,
)

_PACIFIC = ZoneInfo("America/Los_Angeles")


class GeminiRateLimitDetector(LimitDetector):
    """Subscription rate-limit + auth detector for ``gemini`` CLI."""

    def detect(
        self,
        *,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> LimitVerdict:
        combined = f"{stdout}\n{stderr}"

        # Auth: exit code 41 is unambiguous; text fallback for older versions.
        if exit_code == _AUTH_EXIT_CODE or _AUTH_RE.search(combined):
            return AuthRequired(
                reason=(
                    "gemini CLI reports an auth failure; run `gemini /auth` to re-authenticate."
                ),
            )

        if not _QUOTA_RE.search(combined):
            return NoLimit()

        # Quota path: try the three time-format hints in order of specificity.
        rpm_match = _RPM_RE.search(combined)
        if rpm_match is not None:
            seconds = float(rpm_match.group(1))
            return RateLimited(
                reset_at=datetime.now(UTC) + timedelta(seconds=seconds + 5.0),
                reason=f"gemini RPM quota; retry in {seconds:.1f}s",
                kind="rpm",
            )

        rpd_match = _RPD_RE.search(combined)
        if rpd_match is not None:
            reset_at = _parse_rpd_reset(rpd_match)
            return RateLimited(
                reset_at=reset_at,
                reason=(f"gemini RPD quota; reset at {rpd_match.group(0)}"),
                kind="rpd",
            )

        retry_delay_match = _RETRY_DELAY_RE.search(combined)
        if retry_delay_match is not None:
            seconds = int(retry_delay_match.group(1))
            return RateLimited(
                reset_at=datetime.now(UTC) + timedelta(seconds=seconds + 5),
                reason=f"gemini quota; retryDelay={seconds}s",
                kind="rpm",
            )

        # Fallback: assume RPD reset at next midnight Pacific.
        return RateLimited(
            reset_at=_next_midnight_pacific(),
            reason="gemini quota (no time hint); midnight-Pacific fallback",
            kind="rpd",
        )


def _parse_rpd_reset(match: re.Match[str]) -> datetime:
    """Convert ``Access resets at <H>:<M> AM|PM GMT[+-]X[:MM]`` to UTC.

    The wall-clock + GMT offset suffix is enough to compute the reset
    moment unambiguously. We compare against current UTC and roll
    forward a day if the clock-time has already passed today.
    """
    hour = int(match.group(1))
    minute = int(match.group(2))
    ampm = match.group(3).upper()
    offset_hours = int(match.group(4))
    offset_min_str = match.group(5)
    offset_minutes = int(offset_min_str) if offset_min_str else 0

    if ampm == "PM" and hour != 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0

    total_offset_minutes = offset_hours * 60 + (
        offset_minutes if offset_hours >= 0 else -offset_minutes
    )
    tz = timezone(timedelta(minutes=total_offset_minutes))

    now_local = datetime.now(UTC).astimezone(tz)
    candidate = now_local.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC) + timedelta(seconds=60)


def _next_midnight_pacific() -> datetime:
    """Next 00:00 in America/Los_Angeles, returned as aware UTC datetime."""
    now_pst = datetime.now(UTC).astimezone(_PACIFIC)
    tomorrow = (now_pst + timedelta(days=1)).date()
    midnight_local = datetime.combine(tomorrow, time(0, 0), tzinfo=_PACIFIC)
    return midnight_local.astimezone(UTC) + timedelta(seconds=60)
