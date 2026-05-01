"""Unit tests for :class:`GeminiRateLimitDetector`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from selffork_orchestrator.limits.base import (
    AuthRequired,
    NoLimit,
    RateLimited,
)
from selffork_orchestrator.limits.gemini_detector import GeminiRateLimitDetector


class TestQuotaTimeFormats:
    def test_rpm_please_retry_in_seconds(self) -> None:
        # RPM (per-minute) quota signals come with a fractional-second
        # retry hint. Verbatim from gemini-cli issue #8883.
        stderr = "[API Error: 429] Please retry in 15.002899939s. RESOURCE_EXHAUSTED."
        d = GeminiRateLimitDetector()
        verdict = d.detect(stdout="", stderr=stderr, exit_code=1)
        assert isinstance(verdict, RateLimited)
        assert verdict.kind == "rpm"
        delta = verdict.reset_at - datetime.now(UTC)
        # 15s + 5s safety = ~20s.
        assert timedelta(seconds=15) < delta < timedelta(seconds=30)

    def test_rpd_access_resets_at_wall_clock_with_offset(self) -> None:
        stderr = (
            "[API Error: You have exhausted your daily quota on this model.]\n"
            "Usage limit reached for gemini-3-flash-preview. "
            "Access resets at 10:57 PM GMT-3."
        )
        d = GeminiRateLimitDetector()
        verdict = d.detect(stdout="", stderr=stderr, exit_code=1)
        assert isinstance(verdict, RateLimited)
        assert verdict.kind == "rpd"
        # Reset must be in the future (and we expect within a day).
        assert verdict.reset_at > datetime.now(UTC)
        assert verdict.reset_at - datetime.now(UTC) < timedelta(hours=25)

    def test_retry_delay_json_field(self) -> None:
        # Embedded "retryDelay": "30s" inside an error body.
        stderr = (
            'RESOURCE_EXHAUSTED: {"error": {"code": 429, '
            '"status": "RESOURCE_EXHAUSTED", "retryDelay": "30s"}}'
        )
        d = GeminiRateLimitDetector()
        verdict = d.detect(stdout="", stderr=stderr, exit_code=1)
        assert isinstance(verdict, RateLimited)
        delta = verdict.reset_at - datetime.now(UTC)
        assert timedelta(seconds=30) < delta < timedelta(seconds=45)

    def test_quota_without_time_falls_back_to_pacific_midnight(self) -> None:
        # Bare "exceeded your current quota" with no time hint must
        # schedule for the next midnight America/Los_Angeles.
        stderr = "You exceeded your current quota, please check your plan."
        d = GeminiRateLimitDetector()
        verdict = d.detect(stdout="", stderr=stderr, exit_code=1)
        assert isinstance(verdict, RateLimited)
        assert verdict.kind == "rpd"
        # Should be no more than 25 hours out (worst case: just past
        # midnight Pacific in the user's local timezone).
        assert verdict.reset_at > datetime.now(UTC)
        assert verdict.reset_at - datetime.now(UTC) < timedelta(hours=25)


class TestAuth:
    def test_exit_code_41_is_auth_failure(self) -> None:
        # Documented gemini fatal exit code for auth (PR #13728).
        d = GeminiRateLimitDetector()
        verdict = d.detect(stdout="", stderr="", exit_code=41)
        assert isinstance(verdict, AuthRequired)

    def test_text_pattern_fatal_authentication_error(self) -> None:
        d = GeminiRateLimitDetector()
        verdict = d.detect(
            stdout="",
            stderr="FatalAuthenticationError: token expired",
            exit_code=1,
        )
        assert isinstance(verdict, AuthRequired)


class TestNoLimit:
    def test_clean_text_run(self) -> None:
        d = GeminiRateLimitDetector()
        assert isinstance(
            d.detect(stdout="OK\n", stderr="", exit_code=0),
            NoLimit,
        )

    def test_unrelated_error_passes_through(self) -> None:
        # 500 server error etc. is the orchestrator's normal failure path,
        # NOT a quota — the detector must say NoLimit.
        d = GeminiRateLimitDetector()
        verdict = d.detect(
            stdout="",
            stderr="HTTP 500 Internal Server Error",
            exit_code=1,
        )
        assert isinstance(verdict, NoLimit)
