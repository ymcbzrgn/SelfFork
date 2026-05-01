"""Unit tests for :class:`OpenCodeRateLimitDetector`.

Per ``project_cli_provider_routing.md``, this detector intentionally has
NO Anthropic-Pro-via-opencode patterns — Claude routes through the
official ``claude`` CLI exclusively. We test that pattern set deliberately
to prevent regressions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from selffork_orchestrator.limits.base import (
    AuthRequired,
    NoLimit,
    RateLimited,
)
from selffork_orchestrator.limits.opencode_detector import OpenCodeRateLimitDetector


class TestQuotaSignals:
    @pytest.mark.parametrize(
        "stderr",
        [
            'ERROR service=llm error={"statusCode":429,"body":"Too many requests"}',
            'ERROR service=llm error={"code":"rate_limit_exceeded"}',
            "HTTP 429 Too Many Requests",
            "Rate limit exceeded. Please try again later.",
            "OpenAI: insufficient_quota",
            "RESOURCE_EXHAUSTED",
        ],
    )
    def test_quota_phrases_return_rate_limited(self, stderr: str) -> None:
        d = OpenCodeRateLimitDetector()
        verdict = d.detect(stdout="", stderr=stderr, exit_code=1)
        assert isinstance(verdict, RateLimited), (
            f"expected RateLimited for {stderr!r}, got {type(verdict).__name__}"
        )

    def test_retry_after_header_extracts_seconds(self) -> None:
        stderr = '{"statusCode":429, "headers": {"retry-after": "45"}}'
        d = OpenCodeRateLimitDetector()
        verdict = d.detect(stdout="", stderr=stderr, exit_code=1)
        assert isinstance(verdict, RateLimited)
        delta = verdict.reset_at - datetime.now(UTC)
        # 45s + 5s safety = ~50s.
        assert timedelta(seconds=45) < delta < timedelta(seconds=60)

    def test_please_retry_in_seconds(self) -> None:
        stderr = "Rate limit reached. Please retry in 30s."
        d = OpenCodeRateLimitDetector()
        verdict = d.detect(stdout="", stderr=stderr, exit_code=1)
        assert isinstance(verdict, RateLimited)
        delta = verdict.reset_at - datetime.now(UTC)
        assert timedelta(seconds=30) < delta < timedelta(seconds=45)

    def test_zen_default_backoff(self) -> None:
        stderr = "Rate limit exceeded. Please try again later."
        d = OpenCodeRateLimitDetector()
        verdict = d.detect(stdout="", stderr=stderr, exit_code=1)
        assert isinstance(verdict, RateLimited)
        # Zen → 5 minute default backoff.
        delta = verdict.reset_at - datetime.now(UTC)
        assert timedelta(minutes=4, seconds=55) < delta < timedelta(minutes=5, seconds=10)

    def test_openai_class_default_backoff_60s(self) -> None:
        stderr = '{"statusCode":429,"body":"Too many requests"}'
        d = OpenCodeRateLimitDetector()
        verdict = d.detect(stdout="", stderr=stderr, exit_code=1)
        assert isinstance(verdict, RateLimited)
        delta = verdict.reset_at - datetime.now(UTC)
        assert timedelta(seconds=55) < delta < timedelta(seconds=70)


class TestNoClaudePatterns:
    """Regression guards for project_cli_provider_routing memory.

    opencode is non-Claude-only; Claude-Pro phrases must NOT match.
    Otherwise the user routes Claude through opencode incorrectly and
    we mis-attribute their quota.
    """

    @pytest.mark.parametrize(
        "claude_phrase",
        [
            "Claude usage limit reached. Your limit will reset at 2pm (America/New_York)",
            "You're out of extra usage. Add more at claude.ai/settings/usage",
            "Claude AI usage limit reached",
        ],
    )
    def test_claude_only_phrasing_does_not_match(self, claude_phrase: str) -> None:
        d = OpenCodeRateLimitDetector()
        verdict = d.detect(stdout=claude_phrase, stderr="", exit_code=1)
        assert isinstance(verdict, NoLimit), (
            f"opencode detector matched a Claude-only phrase {claude_phrase!r}; "
            "violates project_cli_provider_routing.md"
        )


class TestAuth:
    def test_auth_phrase_returns_auth_required(self) -> None:
        stderr = "AuthError: please run `opencode auth login`"
        d = OpenCodeRateLimitDetector()
        verdict = d.detect(stdout="", stderr=stderr, exit_code=1)
        assert isinstance(verdict, AuthRequired)

    def test_quota_wins_over_auth_when_both_match(self) -> None:
        # opencode misclassifies 429 as auth (issue #15562). When both
        # phrases appear, prefer quota — caller is otherwise stuck in a
        # re-auth loop that doesn't fix anything.
        stderr = (
            'ERROR service=llm error={"statusCode":429}\n'
            "AuthError: please run `opencode auth login`"
        )
        d = OpenCodeRateLimitDetector()
        verdict = d.detect(stdout="", stderr=stderr, exit_code=1)
        assert isinstance(verdict, RateLimited)


class TestNoLimit:
    def test_clean_run(self) -> None:
        d = OpenCodeRateLimitDetector()
        assert isinstance(
            d.detect(stdout="Wrote add.py.\n", stderr="", exit_code=0),
            NoLimit,
        )
