"""Tests for :class:`CodexRateLimitDetector`."""

from __future__ import annotations

from datetime import UTC, datetime

from selffork_orchestrator.limits.base import (
    AuthRequired,
    NoLimit,
    RateLimited,
)
from selffork_orchestrator.limits.codex_detector import CodexRateLimitDetector


def test_no_limit_on_clean_output() -> None:
    detector = CodexRateLimitDetector()
    verdict = detector.detect(
        stdout="Implementation complete.",
        stderr="",
        exit_code=0,
    )
    assert isinstance(verdict, NoLimit)


def test_detects_rate_limit_reached() -> None:
    detector = CodexRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="Error: rate limit reached. Please wait.",
        exit_code=1,
    )
    assert isinstance(verdict, RateLimited)


def test_detects_usage_limit_reached() -> None:
    detector = CodexRateLimitDetector()
    verdict = detector.detect(
        stdout="usage limit reached for ChatGPT Plus",
        stderr="",
        exit_code=1,
    )
    assert isinstance(verdict, RateLimited)


def test_detects_429() -> None:
    detector = CodexRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="HTTP 429 Too Many Requests",
        exit_code=1,
    )
    assert isinstance(verdict, RateLimited)


def test_extracts_retry_hint_seconds() -> None:
    detector = CodexRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="rate limit reached. retry after 600 seconds.",
        exit_code=1,
    )
    assert isinstance(verdict, RateLimited)
    delta = verdict.reset_at - datetime.now(UTC)
    # 600s + 60s safety; allow generous slack for test scheduling.
    assert 590.0 <= delta.total_seconds() <= 700.0


def test_extracts_retry_hint_compound_hours_minutes() -> None:
    detector = CodexRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="rate limit reached. retrying in 2h 45m",
        exit_code=1,
    )
    assert isinstance(verdict, RateLimited)
    delta = verdict.reset_at - datetime.now(UTC)
    # 2h45m = 9900s + 60s safety
    assert 9800.0 <= delta.total_seconds() <= 10100.0


def test_default_5h_fallback_when_no_hint() -> None:
    detector = CodexRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="rate_limit_reached",
        exit_code=1,
    )
    assert isinstance(verdict, RateLimited)
    delta = verdict.reset_at - datetime.now(UTC)
    # 5h = 18000s + 60s safety
    assert 17900.0 <= delta.total_seconds() <= 18200.0


def test_detects_auth_required_login() -> None:
    detector = CodexRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="Error: please run codex login to re-authenticate.",
        exit_code=1,
    )
    assert isinstance(verdict, AuthRequired)


def test_detects_auth_required_401() -> None:
    detector = CodexRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="Error: HTTP 401 Unauthorized — token rejected.",
        exit_code=1,
    )
    assert isinstance(verdict, AuthRequired)


def test_does_not_false_positive_on_user_code_unauthorized_keyword() -> None:
    """Codex stdout often echoes the user's code; an ``unauthorized`` /
    ``401`` literal inside a function name or comment must NOT trigger
    AuthRequired. Tightened regex requires an error-level prefix.
    """
    detector = CodexRateLimitDetector()
    verdict = detector.detect(
        stdout=(
            "def is_unauthorized(user):\n"
            "    # returns 401 Unauthorized for guests\n"
            "    return user.role == 'guest'\n"
            "class InvalidToken(Exception): pass\n"
        ),
        stderr="",
        exit_code=0,
    )
    assert isinstance(verdict, NoLimit)


def test_detects_auth_required_invalid_token() -> None:
    detector = CodexRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="auth.json invalid",
        exit_code=1,
    )
    assert isinstance(verdict, AuthRequired)


def test_rate_limit_takes_precedence_over_auth() -> None:
    """If both signals appear, rate-limit wins (less destructive next action)."""
    detector = CodexRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="rate limit reached. Also please run codex login eventually.",
        exit_code=1,
    )
    assert isinstance(verdict, RateLimited)
