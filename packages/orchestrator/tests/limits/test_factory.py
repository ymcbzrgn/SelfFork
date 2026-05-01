"""Tests for :func:`build_limit_detector`."""

from __future__ import annotations

import pytest

from selffork_orchestrator.limits.claude_detector import ClaudeRateLimitDetector
from selffork_orchestrator.limits.factory import build_limit_detector
from selffork_orchestrator.limits.gemini_detector import GeminiRateLimitDetector
from selffork_orchestrator.limits.opencode_detector import OpenCodeRateLimitDetector


def test_opencode_resolves() -> None:
    assert isinstance(build_limit_detector("opencode"), OpenCodeRateLimitDetector)


def test_claude_code_resolves() -> None:
    assert isinstance(build_limit_detector("claude-code"), ClaudeRateLimitDetector)


def test_gemini_cli_resolves() -> None:
    assert isinstance(build_limit_detector("gemini-cli"), GeminiRateLimitDetector)


def test_unknown_agent_raises() -> None:
    with pytest.raises(ValueError, match="codex"):
        build_limit_detector("codex")


def test_returns_fresh_instance_each_call() -> None:
    a = build_limit_detector("opencode")
    b = build_limit_detector("opencode")
    assert a is not b
