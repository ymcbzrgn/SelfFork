"""Tests for :func:`build_cli_agent`."""

from __future__ import annotations

import pytest

from selffork_orchestrator.cli_agent.factory import build_cli_agent
from selffork_orchestrator.cli_agent.opencode import OpenCodeAgent
from selffork_shared.config import CLIAgentConfig


def test_opencode_resolved() -> None:
    cfg = CLIAgentConfig(agent="opencode")
    agent = build_cli_agent(cfg)
    assert isinstance(agent, OpenCodeAgent)


@pytest.mark.parametrize("agent_name", ["claude-code", "codex", "gemini-cli"])
def test_stubbed_agents_raise(agent_name: str) -> None:
    cfg = CLIAgentConfig(agent=agent_name)  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError):
        build_cli_agent(cfg)
