"""CLI agent adapters — opencode, claude-code, codex, gemini-cli.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.3.
"""

from __future__ import annotations

from selffork_orchestrator.cli_agent.base import CLIAgent
from selffork_orchestrator.cli_agent.claude_code import ClaudeCodeAgent
from selffork_orchestrator.cli_agent.events import (
    AgentEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    ExitEvent,
    StartedEvent,
    ToolCallEvent,
    ToolResultEvent,
    agent_event_adapter,
)
from selffork_orchestrator.cli_agent.factory import build_cli_agent
from selffork_orchestrator.cli_agent.gemini_cli import GeminiCliAgent
from selffork_orchestrator.cli_agent.opencode import OpenCodeAgent

__all__ = [
    "AgentEvent",
    "AssistantMessageEvent",
    "CLIAgent",
    "ClaudeCodeAgent",
    "DoneEvent",
    "ErrorEvent",
    "ExitEvent",
    "GeminiCliAgent",
    "OpenCodeAgent",
    "StartedEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "agent_event_adapter",
    "build_cli_agent",
]
