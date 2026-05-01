"""Backend → implementation resolver for :class:`CLIAgent`."""

from __future__ import annotations

from collections.abc import Mapping

from selffork_orchestrator.cli_agent.base import CLIAgent
from selffork_orchestrator.cli_agent.claude_code import ClaudeCodeAgent
from selffork_orchestrator.cli_agent.codex import CodexAgent
from selffork_orchestrator.cli_agent.gemini_cli import GeminiCliAgent
from selffork_orchestrator.cli_agent.opencode import OpenCodeAgent
from selffork_shared.config import CLIAgentConfig

__all__ = ["build_cli_agent"]

_AGENTS: Mapping[str, type[CLIAgent]] = {
    "opencode": OpenCodeAgent,
    "claude-code": ClaudeCodeAgent,
    "codex": CodexAgent,
    "gemini-cli": GeminiCliAgent,
}


def build_cli_agent(config: CLIAgentConfig) -> CLIAgent:
    """Return a fresh :class:`CLIAgent` instance for ``config.agent``.

    Stubbed agents (claude-code, codex, gemini-cli in MVP v0) raise
    :class:`NotImplementedError` from their constructor; this function lets
    that propagate unchanged.
    """
    cls = _AGENTS.get(config.agent)
    if cls is None:
        # Unreachable: ``config.agent`` is a Pydantic Literal validated at boot.
        raise ValueError(f"unknown CLI agent: {config.agent!r}")
    return cls(config)
