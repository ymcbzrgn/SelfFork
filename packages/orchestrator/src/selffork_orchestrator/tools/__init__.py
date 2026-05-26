"""SelfFork tool registry — what Jr can do beyond chatting.

See ``project_jr_tool_protocol.md`` for the wire format and the
default-tool catalog.
"""

from __future__ import annotations

from selffork_orchestrator.tools.auto_pr import build_auto_pr_tools
from selffork_orchestrator.tools.autopilot import build_autopilot_tools
from selffork_orchestrator.tools.base import (
    ToolArgs,
    ToolCall,
    ToolContext,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    raise_unauthorized,
)
from selffork_orchestrator.tools.body import build_body_tools
from selffork_orchestrator.tools.kanban import build_kanban_tools
from selffork_orchestrator.tools.mind import build_mind_tools
from selffork_orchestrator.tools.parser import parse_tool_calls
from selffork_orchestrator.tools.quota import build_quota_tools
from selffork_orchestrator.tools.router import build_router_tools
from selffork_orchestrator.tools.session import build_session_tools


def build_default_registry() -> ToolRegistry:
    """The canonical registry — every tool the orchestrator wires by default.

    Kanban + Mind from MVP; M3 Order 4 adds the Jr autopilot fleet (quota
    observation + session lifecycle + act tools); M5 Order 4 adds the body
    pillar surface (10 ``body_*`` tools — driver actions gated by warden).
    """
    return ToolRegistry(
        specs=[
            *build_kanban_tools(),
            *build_mind_tools(),
            *build_quota_tools(),
            *build_session_tools(),
            *build_autopilot_tools(),
            *build_body_tools(),
            *build_router_tools(),
            *build_auto_pr_tools(),
        ],
    )


__all__ = [
    "ToolArgs",
    "ToolCall",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "build_auto_pr_tools",
    "build_autopilot_tools",
    "build_body_tools",
    "build_default_registry",
    "build_kanban_tools",
    "build_mind_tools",
    "build_quota_tools",
    "build_router_tools",
    "build_session_tools",
    "parse_tool_calls",
    "raise_unauthorized",
]
