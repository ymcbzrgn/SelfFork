"""Tests for :class:`MinimaxRateLimitDetector`."""

from __future__ import annotations

from datetime import UTC, datetime

from selffork_orchestrator.limits.base import (
    AuthRequired,
    NoLimit,
    RateLimited,
)
from selffork_orchestrator.limits.minimax_detector import MinimaxRateLimitDetector


def test_no_limit_on_clean_output() -> None:
    detector = MinimaxRateLimitDetector()
    verdict = detector.detect(stdout="Done.", stderr="", exit_code=0)
    assert isinstance(verdict, NoLimit)


def test_detects_rate_limit() -> None:
    detector = MinimaxRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="Error: rate limit reached.",
        exit_code=1,
    )
    assert isinstance(verdict, RateLimited)


def test_detects_token_plan_exhausted() -> None:
    detector = MinimaxRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="token plan exhausted for the current 5h window",
        exit_code=1,
    )
    assert isinstance(verdict, RateLimited)


def test_detects_429() -> None:
    detector = MinimaxRateLimitDetector()
    verdict = detector.detect(stdout="", stderr="HTTP 429", exit_code=1)
    assert isinstance(verdict, RateLimited)


def test_detects_auth_login_required() -> None:
    detector = MinimaxRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="please run mmx auth login again.",
        exit_code=1,
    )
    assert isinstance(verdict, AuthRequired)


def test_detects_oauth_token_expired() -> None:
    detector = MinimaxRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="oauth token expired",
        exit_code=1,
    )
    assert isinstance(verdict, AuthRequired)


def test_default_5h_fallback_when_no_hint() -> None:
    detector = MinimaxRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="rate limit reached.",
        exit_code=1,
    )
    assert isinstance(verdict, RateLimited)
    delta = verdict.reset_at - datetime.now(UTC)
    assert 17900.0 <= delta.total_seconds() <= 18200.0


def test_extracts_compound_retry_hint() -> None:
    detector = MinimaxRateLimitDetector()
    verdict = detector.detect(
        stdout="",
        stderr="rate limit reached. retry in 1h 30m",
        exit_code=1,
    )
    assert isinstance(verdict, RateLimited)
    delta = verdict.reset_at - datetime.now(UTC)
    # 1h30m = 5400s + 60s safety
    assert 5300.0 <= delta.total_seconds() <= 5500.0
