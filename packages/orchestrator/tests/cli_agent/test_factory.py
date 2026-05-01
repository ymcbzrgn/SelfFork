"""Tests for :func:`build_cli_agent`."""

from __future__ import annotations

import pytest

from selffork_orchestrator.cli_agent.claude_code import ClaudeCodeAgent
from selffork_orchestrator.cli_agent.factory import build_cli_agent
from selffork_orchestrator.cli_agent.gemini_cli import GeminiCliAgent
from selffork_orchestrator.cli_agent.opencode import OpenCodeAgent
from selffork_shared.config import CLIAgentConfig


def test_opencode_resolved() -> None:
    cfg = CLIAgentConfig(agent="opencode")
    agent = build_cli_agent(cfg)
    assert isinstance(agent, OpenCodeAgent)


def test_claude_code_resolved() -> None:
    cfg = CLIAgentConfig(agent="claude-code")
    agent = build_cli_agent(cfg)
    assert isinstance(agent, ClaudeCodeAgent)


def test_gemini_cli_resolved() -> None:
    cfg = CLIAgentConfig(agent="gemini-cli")
    agent = build_cli_agent(cfg)
    assert isinstance(agent, GeminiCliAgent)


def test_codex_still_stubbed() -> None:
    # codex remains a NotImplementedError stub in MVP — only opencode,
    # claude-code, and gemini-cli are first-class per
    # project_selffork_jr_drives_3_cli_agents.md.
    cfg = CLIAgentConfig(agent="codex")
    with pytest.raises(NotImplementedError):
        build_cli_agent(cfg)
