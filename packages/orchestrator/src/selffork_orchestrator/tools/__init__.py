"""SelfFork tool registry — what Jr can do beyond chatting.

See ``project_jr_tool_protocol.md`` for the wire format and the
default-tool catalog.
"""

from __future__ import annotations

from selffork_orchestrator.tools.base import (
    ToolArgs,
    ToolCall,
    ToolContext,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    raise_unauthorized,
)
from selffork_orchestrator.tools.kanban import build_kanban_tools
from selffork_orchestrator.tools.parser import parse_tool_calls


def build_default_registry() -> ToolRegistry:
    """The canonical registry — every tool the orchestrator wires by default."""
    return ToolRegistry(specs=[*build_kanban_tools()])


__all__ = [
    "ToolArgs",
    "ToolCall",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "build_default_registry",
    "build_kanban_tools",
    "parse_tool_calls",
    "raise_unauthorized",
]
