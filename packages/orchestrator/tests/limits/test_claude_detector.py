"""Unit tests for :class:`ClaudeRateLimitDetector`."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from selffork_orchestrator.limits.base import (
    AuthRequired,
    NoLimit,
    RateLimited,
)
from selffork_orchestrator.limits.claude_detector import ClaudeRateLimitDetector


class TestStreamJsonPath:
    def test_rate_limit_event_returns_rate_limited(self) -> None:
        event = {
            "type": "system",
            "subtype": "api_retry",
            "attempt": 1,
            "max_retries": 10,
            "retry_delay_ms": 5000,
            "error_status": 429,
            "error": "rate_limit",
        }
        stdout = json.dumps(event) + "\n"
        d = ClaudeRateLimitDetector()
        verdict = d.detect(stdout=stdout, stderr="", exit_code=1)
        assert isinstance(verdict, RateLimited)
        assert "rate_limit" in verdict.reason.lower()
        # Default fallback when stream-json carries no time = now + 5h.
        delta = verdict.reset_at - datetime.now(UTC)
        assert timedelta(hours=4, minutes=55) < delta < timedelta(hours=5, minutes=5)

    @pytest.mark.parametrize(
        "auth_error",
        ["authentication_failed", "oauth_org_not_allowed"],
    )
    def test_auth_errors_return_auth_required(self, auth_error: str) -> None:
        event = {
            "type": "system",
            "subtype": "api_retry",
            "error_status": 401,
            "error": auth_error,
        }
        stdout = json.dumps(event) + "\n"
        d = ClaudeRateLimitDetector()
        verdict = d.detect(stdout=stdout, stderr="", exit_code=1)
        assert isinstance(verdict, AuthRequired)
        assert auth_error in verdict.reason

    def test_unrelated_error_enum_returns_no_limit(self) -> None:
        # server_error / billing_error / max_output_tokens are real Claude
        # errors but the detector intentionally lets the orchestrator
        # surface them via the normal exit-code path — not as quota.
        event = {
            "type": "system",
            "subtype": "api_retry",
            "error_status": 500,
            "error": "server_error",
        }
        stdout = json.dumps(event) + "\n"
        d = ClaudeRateLimitDetector()
        assert isinstance(
            d.detect(stdout=stdout, stderr="", exit_code=1),
            NoLimit,
        )

    def test_malformed_jsonl_lines_are_skipped(self) -> None:
        # Detector must not crash on lines that aren't JSON objects.
        stdout = (
            "this is plain text\n"
            "{not-json-at-all\n"
            '{"type": "system", "subtype": "thinking"}\n'  # ignored subtype
            "Claude usage limit reached. Your limit will reset at 2pm (America/New_York)\n"
        )
        d = ClaudeRateLimitDetector()
        verdict = d.detect(stdout=stdout, stderr="", exit_code=0)
        # Falls through to the text path (verbatim usage-limit string).
        assert isinstance(verdict, RateLimited)


class TestTextPath:
    def test_subscription_limit_with_iana_tz(self) -> None:
        text = (
            "Some leading output...\n"
            "Claude usage limit reached. Your limit will reset at 2pm "
            "(America/New_York)\n"
        )
        d = ClaudeRateLimitDetector()
        verdict = d.detect(stdout=text, stderr="", exit_code=0)
        assert isinstance(verdict, RateLimited)
        assert "2pm" in verdict.reason
        assert "America/New_York" in verdict.reason
        # Reset must be in the future (we add safety margin).
        assert verdict.reset_at > datetime.now(UTC)
        # And within ~24h ahead (tz wall-clock can roll a day).
        assert verdict.reset_at - datetime.now(UTC) < timedelta(hours=25)

    def test_legacy_claude_ai_phrasing(self) -> None:
        # Pre-2025 wording observed in older issue reports.
        text = "Claude AI usage limit reached. Your limit will reset at 5pm (Europe/Kyiv)"
        d = ClaudeRateLimitDetector()
        verdict = d.detect(stdout="", stderr=text, exit_code=0)
        assert isinstance(verdict, RateLimited)

    def test_burst_limiter_is_not_quota(self) -> None:
        # Server temporarily limiting requests is NOT a subscription quota.
        # Returning RateLimited here would trigger a multi-hour pause for a
        # 30-second issue — verified anti-pattern from claude-code #53922.
        text = "Server is temporarily limiting requests (not your usage limit) · Rate limited"
        d = ClaudeRateLimitDetector()
        verdict = d.detect(stdout=text, stderr="", exit_code=1)
        assert isinstance(verdict, NoLimit)

    def test_auth_phrase_returns_auth_required(self) -> None:
        text = "authentication failed; please re-login by running `claude login`"
        d = ClaudeRateLimitDetector()
        verdict = d.detect(stdout="", stderr=text, exit_code=1)
        assert isinstance(verdict, AuthRequired)

    def test_invalid_tz_falls_back_to_5h(self) -> None:
        # Malformed or unknown timezone names must not crash; we fall
        # back to ``now + 5h`` (Anthropic's default Pro/Max window).
        text = "Claude usage limit reached. Your limit will reset at 2pm (Not/A_Real_Zone)"
        d = ClaudeRateLimitDetector()
        verdict = d.detect(stdout=text, stderr="", exit_code=0)
        assert isinstance(verdict, RateLimited)
        delta = verdict.reset_at - datetime.now(UTC)
        assert timedelta(hours=4, minutes=55) < delta < timedelta(hours=5, minutes=5)


class TestNoLimitPath:
    def test_clean_run_returns_no_limit(self) -> None:
        d = ClaudeRateLimitDetector()
        assert isinstance(
            d.detect(
                stdout="All good. Created hello.py.\n",
                stderr="",
                exit_code=0,
            ),
            NoLimit,
        )
