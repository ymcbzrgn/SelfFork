"""CodexRateLimitDetector — rate-limit + auth detection for ``codex`` CLI.

Codex CLI's primary rate-limit signal is the per-turn ``TokenCountEvent``
in the rollout JSONL (consumed by :class:`CodexSnapper` for proactive
quota state). The exec-mode stdout/stderr surface that this detector
parses is the *reactive* path: when SelfFork has just executed a Codex
turn and needs to classify the resulting (stdout, stderr, exit_code)
into NoLimit / RateLimited / AuthRequired.

We use stderr-priority text regex because:

  - ``codex exec --json`` rate_limits field is null (Issue #14728 — open).
  - Reactive path runs once per turn; cheap regex is the right call.
  - Reset semantics are coarse here — the proactive Snapper emits
    precise ``resets_in_seconds`` from rollout JSONL; this detector
    falls back to ``now + 5h`` (Codex Plus primary window) when no
    explicit retry hint is present.

Auth detection mirrors ``claude_detector.py``: look for messages telling
the user to re-login (``codex login``).
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

__all__ = ["CodexRateLimitDetector"]

# Subscription quota hits. Codex error envelopes seen in the wild:
#   "rate limit reached"
#   "rate_limit_exceeded"
#   "RateLimitReached"
#   "usage limit reached"
#   "Too Many Requests" (429 surface)
_RATE_LIMIT_RE = re.compile(
    r"(rate[\s_-]?limit[\s_-]?(?:reached|exceeded)"
    r"|RateLimitReached"
    r"|usage[\s_-]?limit[\s_-]?reached"
    r"|too[\s_-]?many[\s_-]?requests"
    r"|http\s+429)",
    re.IGNORECASE,
)

# Auth failures. Codex prompts ``codex login`` on token expiry; we also
# accept generic 401/unauthorized hints. Generic auth keywords
# (``unauthorized``, ``invalid_token``, ``http 401``) are sentence-anchored
# behind an error-level prefix (``error:``, ``fatal:``, ``please``) so a
# user file containing the literal word "unauthorized" or a
# ``# returns 401 Unauthorized`` code comment in codex's stdout doesn't
# trigger a false-positive AuthRequired verdict.
_AUTH_RE = re.compile(
    r"(please[\s_-]?(?:re-?)?login"
    r"|run\s+`?codex\s+login`?"
    r"|auth(?:\.json)?\s+(?:missing|invalid|expired)"
    r"|(?:error|fatal|warn(?:ing)?)\s*[:!-]?\s*"
    r"(?:.*?\b(?:http\s+401|unauthorized|invalid[\s_-]?token))"
    r"|oauth[\s_-]?token[\s_-]?expired)",
    re.IGNORECASE,
)

# Reset hint patterns. Codex error envelopes typically say
#   "retrying in 2h 45m"
#   "retry after 600 seconds"
#   "reset in 12345 seconds"
_RETRY_HINT_RE = re.compile(
    r"(?:retry(?:ing)?\s+(?:in|after)|resets?\s+in)\s+"
    r"(?:(\d+)\s*h(?:ours?)?[,\s]*)?"
    r"(?:(\d+)\s*m(?:in(?:utes?)?)?[,\s]*)?"
    r"(?:(\d+)\s*s(?:ec(?:onds?)?)?)?",
    re.IGNORECASE,
)

# Codex Plus primary window when no explicit retry hint is present.
_DEFAULT_RESET = timedelta(hours=5)
# Tiny safety margin so we don't poke the API exactly when the window opens.
_RESET_SAFETY = timedelta(seconds=60)


class CodexRateLimitDetector(LimitDetector):
    """Subscription rate-limit + auth detector for ``codex`` CLI."""

    def detect(
        self,
        *,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> LimitVerdict:
        del exit_code  # rate-limit signal is in output, not exit code.
        combined = f"{stdout}\n{stderr}"

        if _RATE_LIMIT_RE.search(combined):
            reset_at = self._extract_reset_at(combined)
            return RateLimited(
                reset_at=reset_at,
                reason="codex CLI reported rate limit / usage cap",
                kind="unknown",  # text path can't disambiguate primary vs secondary
            )

        if _AUTH_RE.search(combined):
            return AuthRequired(
                reason=("codex CLI reports an auth failure; run `codex login` to re-authenticate."),
            )

        return NoLimit()

    @staticmethod
    def _extract_reset_at(text: str) -> datetime:
        """Best-effort retry-hint parser. Falls back to now + 5h."""
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
