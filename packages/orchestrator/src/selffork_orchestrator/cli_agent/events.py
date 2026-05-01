"""Agent event types — discriminated union of what a CLI agent can emit.

Every :meth:`CLIAgent.parse_event` call returns either a member of
:data:`AgentEvent` (a tagged union over the categories below) or ``None``
for unparseable / non-event lines (banner, progress noise, blank lines).

The orchestrator consumes these events to (a) drive the session lifecycle
state machine, (b) update the plan-as-state document, (c) write audit
records.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.3.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

__all__ = [
    "AgentEvent",
    "AssistantMessageEvent",
    "DoneEvent",
    "ErrorEvent",
    "ExitEvent",
    "StartedEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "agent_event_adapter",
]


class _BaseEvent(BaseModel):
    """Permissive base for events.

    We keep ``extra='allow'`` so backend-specific fields the orchestrator
    doesn't yet model are preserved on the event for audit logging,
    instead of being silently discarded.
    """

    model_config = ConfigDict(extra="allow")


class StartedEvent(_BaseEvent):
    """Agent reports that its session is up and ready."""

    type: Literal["started"] = "started"
    session_id: str | None = None


class AssistantMessageEvent(_BaseEvent):
    """Agent emitted an assistant-side message (text, possibly partial)."""

    type: Literal["assistant_message"] = "assistant_message"
    text: str


class ToolCallEvent(_BaseEvent):
    """Agent invoked a tool (file edit, shell exec, web fetch, etc.)."""

    type: Literal["tool_call"] = "tool_call"
    tool_name: str
    call_id: str | None = None
    args: dict[str, object] = Field(default_factory=dict)


class ToolResultEvent(_BaseEvent):
    """Agent received a result from a previous tool call."""

    type: Literal["tool_result"] = "tool_result"
    tool_name: str | None = None
    call_id: str | None = None
    success: bool = True
    output: str | None = None


class ErrorEvent(_BaseEvent):
    """Agent surfaced a non-fatal error event in its stream."""

    type: Literal["error"] = "error"
    message: str
    detail: str | None = None


class DoneEvent(_BaseEvent):
    """Agent reports that it has finished its work successfully."""

    type: Literal["done"] = "done"
    summary: str | None = None


class ExitEvent(_BaseEvent):
    """Synthesized when the CLI subprocess exits.

    Not produced by the agent itself — the orchestrator emits this once
    ``proc.wait()`` returns, so audit consumers see a uniform final event
    regardless of how the session ended.
    """

    type: Literal["exit"] = "exit"
    code: int


AgentEvent = Annotated[
    StartedEvent
    | AssistantMessageEvent
    | ToolCallEvent
    | ToolResultEvent
    | ErrorEvent
    | DoneEvent
    | ExitEvent,
    Field(discriminator="type"),
]


# Module-level adapter so consumers can validate dicts without re-creating
# the TypeAdapter on every parse.
agent_event_adapter: TypeAdapter[AgentEvent] = TypeAdapter(AgentEvent)
