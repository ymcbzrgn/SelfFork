"""Tests for :func:`build_cli_agent`."""

from __future__ import annotations

from selffork_orchestrator.cli_agent.claude_code import ClaudeCodeAgent
from selffork_orchestrator.cli_agent.codex import CodexAgent
from selffork_orchestrator.cli_agent.factory import build_cli_agent
from selffork_orchestrator.cli_agent.gemini_cli import GeminiCliAgent
from selffork_orchestrator.cli_agent.minimax_cli import MinimaxCliAgent
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


def test_codex_resolved() -> None:
    # codex is now first-class as of M3 (CLI Surfing) — see ARGE 2026-05-09
    # and project_yamac_jr_drives_3_cli_agents memory (Codex CLI for ChatGPT
    # Plus auth, replacing the stub from MVP v0).
    cfg = CLIAgentConfig(agent="codex")
    agent = build_cli_agent(cfg)
    assert isinstance(agent, CodexAgent)


def test_minimax_cli_resolved() -> None:
    # mmx-cli — Order 7 (M3): Yamaç's Minimax subscription via OAuth.
    cfg = CLIAgentConfig(agent="minimax-cli")
    agent = build_cli_agent(cfg)
    assert isinstance(agent, MinimaxCliAgent)
