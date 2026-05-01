"""OpenCodeRateLimitDetector — quota + auth detection for ``opencode`` CLI.

Per ``project_cli_provider_routing.md`` (2026-05-01), opencode is used
ONLY with non-Anthropic providers (ChatGPT, Minimax, GLM, opencode Zen
free tier). Claude Pro/Max routes through the official ``claude`` CLI,
NEVER through opencode. So this detector intentionally does NOT carry
any Anthropic-Pro-via-opencode patterns ("Claude usage limit reached",
"out of extra usage").

Detection strategy from selffork-researcher 2026-05-01:

- ``--format json`` emits success events only (step_start / text /
  step_finish). NO error envelope is documented; we do NOT rely on it
  for limit detection.
- Stderr regex against a **provider-aware** map covering the four
  providers we actually use:
    - **OpenAI / ChatGPT / OpenRouter**: ``"statusCode":429``,
      ``"insufficient_quota"``, ``"Rate limit reached"``,
      ``"Too Many Requests"``.
    - **Minimax / GLM / generic OpenAI-compat**: same 429 +
      ``"rate_limit_exceeded"`` (Azure-style envelope can come over
      HTTP 200, so we match the body too).
    - **opencode Zen** (free tier): ``"Rate limit exceeded.
      Please try again later."``.
- Auth heuristics: ``opencode auth login``, ``unauthorized``, ``401``,
  ``invalid_api_key``.

Reset-time format: opencode passes provider strings through verbatim,
so we look for embedded hints (``retry-after``, ``retryDelay``); if
none found, fall back to a fixed 60s for OpenAI-class quotas (most
common pattern) or 5min for Zen.

CRITICAL caveat (issue sst/opencode#8203): opencode can HANG forever on
429 instead of exiting. The orchestrator's CLI exec layer is responsible
for wrapping with a wall-clock timeout; this detector only classifies
the captured output once exec returns.
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

__all__ = ["OpenCodeRateLimitDetector"]

# Quota/rate-limit signals across the providers we actually use through
# opencode. Verbatim phrases come from upstream issue tracker quotes
# (selffork-researcher 2026-05-01).
_QUOTA_RE = re.compile(
    r"("
    r"\"statusCode\"\s*:\s*429"
    r"|\bcode\s*[:=]\s*[\"']?429[\"']?"
    r"|\b429\b\s*Too\s*Many\s*Requests"
    r"|\bToo\s+Many\s+Requests\b"
    r"|\brate.?limit.?exceeded\b"
    r"|\bRate\s+limit\s+exceeded\b"
    r"|\bRate\s+limit\s+reached\b"
    r"|\binsufficient_quota\b"
    r"|\bquota.?exceeded\b"
    r"|\bRESOURCE_EXHAUSTED\b"
    r")",
    re.IGNORECASE,
)

# Auth heuristic. opencode often misclassifies 429 as auth (#15562) so we
# require auth-specific phrasing — bare "401" alone isn't enough if the
# quota regex also fires.
_AUTH_RE = re.compile(
    r"("
    r"opencode\s+auth\s+login"
    r"|invalid_api_key"
    r"|missing\s+api\s+key"
    r"|unauthorized\s*\(401\)"
    r"|authentication.?(?:failed|required)"
    r"|\bAuthError\b"
    r")",
    re.IGNORECASE,
)

# Provider-passthrough hints for retry timing. Keep simple — most OpenAI-
# compat providers either carry a "retry-after: <seconds>" header value or
# a "Please retry in <s>s" gemini-style string. We accept both.
_RETRY_AFTER_HEADER_RE = re.compile(
    r"retry[-_]after[\"']?\s*[:=]\s*[\"']?(\d+)(?:\.\d+)?",
    re.IGNORECASE,
)
_RETRY_PLEASE_RE = re.compile(
    r"(?:Please\s+retry\s+in|try\s+again\s+in)\s+(\d+(?:\.\d+)?)\s*s\b",
    re.IGNORECASE,
)

# Default backoff when no time hint is present, by provider hint. We
# heuristic-classify from the matched phrase: Zen, OpenAI-class, generic.
_DEFAULT_BACKOFF_OPENAI = timedelta(seconds=60)
_DEFAULT_BACKOFF_ZEN = timedelta(minutes=5)
_DEFAULT_BACKOFF_GENERIC = timedelta(seconds=120)


class OpenCodeRateLimitDetector(LimitDetector):
    """Quota + auth detector for ``opencode`` CLI (non-Anthropic providers)."""

    def detect(
        self,
        *,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> LimitVerdict:
        del exit_code  # opencode hangs/exits inconsistently; not a signal.
        combined = f"{stdout}\n{stderr}"

        quota_hit = _QUOTA_RE.search(combined)
        auth_hit = _AUTH_RE.search(combined)

        # Quota wins over auth when both fire — mitigates the misclassification
        # documented in opencode issue #15562 where 429 looks like auth failure.
        if quota_hit is not None:
            backoff = _resolve_backoff(combined)
            return RateLimited(
                reset_at=datetime.now(UTC) + backoff,
                reason=f"opencode quota; matched {quota_hit.group(1)!r}",
                kind="rpm" if backoff <= timedelta(minutes=2) else "unknown",
            )

        if auth_hit is not None:
            return AuthRequired(
                reason=(
                    "opencode reports an auth failure; "
                    "run `opencode auth login` to re-authenticate."
                ),
            )

        return NoLimit()


def _resolve_backoff(text: str) -> timedelta:
    """Pick the best backoff hint we can find in ``text``.

    Returns the shortest sane backoff that covers the longest hint we
    saw, so a noisy stderr never schedules a multi-hour wait when the
    provider clearly said "retry in 30s". The chain of fallbacks:

    1. ``retry-after: <n>`` header → exact seconds + 5s safety.
    2. ``Please retry in <n>s`` text → exact seconds + 5s safety.
    3. Heuristic provider hint:
       - opencode Zen → 5 min.
       - OpenAI-class (statusCode 429 in JSON envelope) → 60 s.
       - Otherwise → 120 s.
    """
    safety = timedelta(seconds=5)

    m = _RETRY_AFTER_HEADER_RE.search(text)
    if m is not None:
        return timedelta(seconds=float(m.group(1))) + safety

    m = _RETRY_PLEASE_RE.search(text)
    if m is not None:
        return timedelta(seconds=float(m.group(1))) + safety

    if "opencode zen" in text.lower() or "Rate limit exceeded. Please try again later" in text:
        return _DEFAULT_BACKOFF_ZEN
    if '"statusCode":429' in text or "statusCode: 429" in text:
        return _DEFAULT_BACKOFF_OPENAI
    return _DEFAULT_BACKOFF_GENERIC
