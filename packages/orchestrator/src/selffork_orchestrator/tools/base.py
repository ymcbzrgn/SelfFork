"""Tool registry primitives — :class:`ToolSpec`, :class:`ToolRegistry`.

Per ``project_jr_tool_protocol.md`` SelfFork Jr emits structured tool
calls inside fenced ``<selffork-tool-call>`` JSON blocks. The parser
extracts those calls (see :mod:`tools.parser`); this module is the
**registry** — what tools exist, what their args look like, and how to
invoke them.

Design choices:

- **Pydantic-validated args.** Each tool declares its args as a Pydantic
  model. The registry validates Jr's raw arg dict against the model
  before invoking — invalid args become a :class:`ToolResult` with
  status="invalid_args" rather than a Python exception.
- **Sync handlers.** Tools are filesystem operations (kanban writes,
  future: git, pytest). Async handlers would be over-engineering.
- **No auto-discovery.** Adding a new tool means importing it + adding
  it to ``ToolRegistry.default()``. Explicit > implicit.
- **Result is always a dict.** The aggregator that splices results back
  into Jr's chat history wants a uniform shape; per-tool result types
  would mean N branches at the call site.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

__all__ = [
    "ToolCall",
    "ToolHandler",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
]

# A handler runs the tool. It receives a ``Context`` (whatever the
# orchestrator wires in — typically a small dataclass with the active
# session's project_slug + ProjectStore reference) and the parsed,
# validated args. Returns a JSON-serialisable result dict.
ToolHandler = Callable[["ToolContext", BaseModel], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Per-call context handed to a tool handler.

    Attributes:
        session_id: id of the parent SelfFork-Jr session emitting the
            tool call. Recorded in audit events + may be stamped onto
            the artifact the tool writes (e.g. kanban card's
            ``last_touched_by_session_id``).
        project_slug: when the parent session is bound to a project,
            this is its slug. ``None`` for orphan sessions; tools that
            require a project return an error in that case.
        project_store: the active :class:`ProjectStore` instance.
            Wired in by the orchestrator at registry construction
            time — handlers don't import it directly.
    """

    session_id: str
    project_slug: str | None
    project_store: object  # selffork_orchestrator.projects.ProjectStore


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One parsed tool call from a Jr reply.

    Attributes:
        tool: the tool name from the call's JSON.
        args: the raw args dict, BEFORE Pydantic validation.
        order_in_reply: 0-based position so we can preserve invocation
            order across multiple calls in one reply.
    """

    tool: str
    args: dict[str, Any]
    order_in_reply: int


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The outcome of one :class:`ToolCall` after handler invocation.

    The orchestrator turns this into a ``tool.result`` audit event AND
    a chunk of text appended to Jr's next user-role message so the LLM
    can react.

    ``status`` semantics:

    - ``ok``: handler ran, ``payload`` carries its return value.
    - ``invalid_args``: args dict failed Pydantic validation; ``error``
      explains which field.
    - ``unknown_tool``: ``tool`` name isn't in the registry.
    - ``handler_error``: handler raised; ``error`` is the message.
    - ``unauthorized``: handler refused (e.g. no project context for a
      project-scoped tool).
    """

    tool: str
    status: Literal["ok", "invalid_args", "unknown_tool", "handler_error", "unauthorized"]
    payload: dict[str, Any] | None = None
    error: str | None = None


class ToolSpec[A: BaseModel]:
    """One tool's contract: name + args schema + handler.

    Generic over the args model class so type checkers can verify each
    handler against its declared schema.
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        args_model: type[A],
        handler: Callable[[ToolContext, A], dict[str, Any]],
    ) -> None:
        if not name or " " in name:
            raise ValueError(
                f"tool name {name!r} must be non-empty and contain no spaces",
            )
        self.name = name
        self.description = description
        self.args_model: type[A] = args_model
        # Wrap the typed handler in a BaseModel-typed handler so the
        # registry can store handlers uniformly.

        def _erased(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
            assert isinstance(args, args_model), (  # noqa: S101 — internal invariant
                f"handler for {name} got args of type "
                f"{type(args).__name__}, expected {args_model.__name__}"
            )
            return handler(ctx, args)

        self.handler: ToolHandler = _erased

    def json_schema(self) -> dict[str, Any]:
        """Pydantic-derived JSON schema for the args model. Used in
        the system prompt's tool catalog so Jr knows the call shape.
        """
        return self.args_model.model_json_schema()


class ToolRegistry:
    """Container of available tools, queried by name."""

    def __init__(self, specs: list[ToolSpec[Any]] | None = None) -> None:
        self._tools: dict[str, ToolSpec[Any]] = {}
        for spec in specs or []:
            self.register(spec)

    def register(self, spec: ToolSpec[Any]) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name!r} already registered")
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> ToolSpec[Any] | None:
        return self._tools.get(name)

    def catalog(self) -> list[dict[str, Any]]:
        """Catalog suitable for injecting into Jr's system prompt."""
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "args_schema": spec.json_schema(),
            }
            for spec in self._tools.values()
        ]

    def invoke(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        """Validate args + invoke the handler. Always returns a result —
        never raises (handler exceptions are captured as ``handler_error``).
        """
        spec = self._tools.get(call.tool)
        if spec is None:
            return ToolResult(
                tool=call.tool,
                status="unknown_tool",
                error=(f"tool {call.tool!r} is not registered; known tools: {self.names()}"),
            )
        try:
            args = spec.args_model.model_validate(call.args)
        except ValidationError as exc:
            return ToolResult(
                tool=call.tool,
                status="invalid_args",
                error=str(exc),
            )
        try:
            payload = spec.handler(ctx, args)
        except _UnauthorizedError as exc:
            return ToolResult(
                tool=call.tool,
                status="unauthorized",
                error=str(exc),
            )
        except Exception as exc:
            return ToolResult(
                tool=call.tool,
                status="handler_error",
                error=f"{type(exc).__name__}: {exc}",
            )
        return ToolResult(tool=call.tool, status="ok", payload=payload)


class _UnauthorizedError(RuntimeError):
    """Raised by handlers that need a project context but don't have one."""


def raise_unauthorized(message: str) -> None:
    """Helper for tool handlers — surfaces a typed unauthorized result."""
    raise _UnauthorizedError(message)


# A mixin-y base for "args" Pydantic models. Doesn't enforce extra=
# forbid because tools that grow optional fields shouldn't break old
# Jr training data — but each tool is free to specify its own
# ConfigDict(extra="forbid") if it wants strict args.
class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
