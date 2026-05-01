"""Subscription rate-limit detection — per-CLI detectors + scheduling.

Each CLI agent (``claude``, ``gemini``, ``opencode``) has known quota
signals; the matching :class:`LimitDetector` parses them out of the
captured exec output and returns a :class:`LimitVerdict`. The
orchestrator persists ``RateLimited`` verdicts as scheduled-resume
records so a daemon (``selffork resume watch``) can reopen the session
when the reset window arrives.

See: ``packages/orchestrator/src/selffork_orchestrator/limits/base.py``.
"""

from __future__ import annotations

from selffork_orchestrator.limits.base import (
    AuthRequired,
    LimitDetector,
    LimitVerdict,
    NoLimit,
    RateLimited,
)
from selffork_orchestrator.limits.claude_detector import ClaudeRateLimitDetector
from selffork_orchestrator.limits.factory import build_limit_detector
from selffork_orchestrator.limits.gemini_detector import GeminiRateLimitDetector
from selffork_orchestrator.limits.opencode_detector import OpenCodeRateLimitDetector

__all__ = [
    "AuthRequired",
    "ClaudeRateLimitDetector",
    "GeminiRateLimitDetector",
    "LimitDetector",
    "LimitVerdict",
    "NoLimit",
    "OpenCodeRateLimitDetector",
    "RateLimited",
    "build_limit_detector",
]
