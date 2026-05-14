"""MinimaxRateLimitDetector — rate-limit + auth detection for ``mmx`` CLI.

Reactive path (post-exec): inspect (stdout, stderr, exit_code) to classify.
Proactive path (per-tick): :class:`MinimaxSnapper` reads the Token Plan
``/v1/token_plan/remains`` endpoint via OAuth Bearer.

Reset semantics: Token Plan primary window is 5h rolling (per ARGE
2026-05-09 + Verdent guide); we fall back to ``now + 5h`` when no
explicit retry hint is present in the error envelope.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from selffork_orchestrator.limits.base import (
    AuthRequired,
    LimitDetector,
    LimitVerdict,
    NoLimit,
    RateLimited,
)

__all__ = ["MinimaxRateLimitDetector"]

# Subscription quota hits. Anthropic-compatible endpoint surface, so
# common rate-limit phrasings translate; we also accept Minimax-specific
# token plan phrasings.
_RATE_LIMIT_RE = re.compile(
    r"(rate[\s_-]?limit[\s_-]?(?:reached|exceeded)"
    r"|token[\s_-]?plan[\s_-]?(?:exhausted|exceeded)"
    r"|usage[\s_-]?limit[\s_-]?reached"
    r"|too[\s_-]?many[\s_-]?requests"
    r"|http\s+429)",
    re.IGNORECASE,
)

# Auth failures. ``mmx`` prompts ``mmx auth login`` on token expiry.
_AUTH_RE = re.compile(
    r"(please[\s_-]?(?:re-?)?login"
    r"|run\s+`?mmx\s+auth\s+login`?"
    r"|credentials\.json\s+(?:missing|invalid|expired)"
    r"|http\s+401"
    r"|unauthorized"
    r"|invalid[\s_-]?token"
    r"|oauth[\s_-]?token[\s_-]?expired)",
    re.IGNORECASE,
)

# Reset hint patterns (compound h/m/s, like Codex).
_RETRY_HINT_RE = re.compile(
    r"(?:retry(?:ing)?\s+(?:in|after)|resets?\s+in)\s+"
    r"(?:(\d+)\s*h(?:ours?)?[,\s]*)?"
    r"(?:(\d+)\s*m(?:in(?:utes?)?)?[,\s]*)?"
    r"(?:(\d+)\s*s(?:ec(?:onds?)?)?)?",
    re.IGNORECASE,
)

_DEFAULT_RESET = timedelta(hours=5)
_RESET_SAFETY = timedelta(seconds=60)


class MinimaxRateLimitDetector(LimitDetector):
    """Subscription rate-limit + auth detector for ``mmx`` CLI."""

    def detect(
        self,
        *,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> LimitVerdict:
        del exit_code
        combined = f"{stdout}\n{stderr}"

        if _RATE_LIMIT_RE.search(combined):
            reset_at = self._extract_reset_at(combined)
            return RateLimited(
                reset_at=reset_at,
                reason="mmx CLI reported rate limit / token plan exhausted",
                kind="unknown",
            )

        if _AUTH_RE.search(combined):
            return AuthRequired(
                reason=(
                    "mmx CLI reports an auth failure; run `mmx auth login` to re-authenticate."
                ),
            )

        return NoLimit()

    @staticmethod
    def _extract_reset_at(text: str) -> datetime:
        now_utc = datetime.now(UTC)
        match = _RETRY_HINT_RE.search(text)
        if match is None:
            return now_utc + _DEFAULT_RESET + _RESET_SAFETY
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        delta_seconds = hours * 3600 + minutes * 60 + seconds
        if delta_seconds <= 0:
            return now_utc + _DEFAULT_RESET + _RESET_SAFETY
        return now_utc + timedelta(seconds=delta_seconds) + _RESET_SAFETY
