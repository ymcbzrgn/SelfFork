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

import inspect
from collections.abc import Awaitable, Callable
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
# validated args. Returns either a JSON-serialisable result dict OR an
# awaitable that resolves to one. Sync handlers are the common case
# (kanban filesystem operations); async handlers exist for tools that
# bridge to async I/O (Mind store, embedders) — the registry's
# ``invoke_async`` resolves both transparently.
ToolHandler = Callable[
    ["ToolContext", BaseModel],
    "dict[str, Any] | Awaitable[dict[str, Any]]",
]


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
        mind_store: optional :class:`MindStore` for Mind-aware tools
            (``mind_recall``, ``mind_note_add``). ``None`` when Mind is
            disabled at the boot path; tools must return an
            ``unauthorized`` :class:`ToolResult` rather than raise.
        mind_retriever: optional retriever for ``mind_recall``. ``None``
            when Mind is disabled.
        episodic_writer: optional Mind T2 writer for ``mind_note_add``.
            ``None`` when Mind is disabled.
        cli_agent_name: human label of the active CLI agent
            (``"claude-code"`` / ``"gemini-cli"`` / ``"opencode"`` /
            ``"codex"``); used by Mind T2 tag generation when this
            session writes notes.
    """

    session_id: str
    project_slug: str | None
    project_store: object  # selffork_orchestrator.projects.ProjectStore
    mind_store: object | None = None  # selffork_mind.store.MindStore
    mind_retriever: object | None = None  # selffork_mind.rag.HybridRetriever
    episodic_writer: object | None = None  # selffork_mind.memory.tiers.EpisodicWriter
    cli_agent_name: str | None = None
    # M3 Order 4 — Jr autopilot dependencies. All optional, None when the
    # corresponding subsystem isn't wired (e.g. snappers off, non-macOS host
    # without launchd, no Telegram bot token so the null bridge is used).
    proactive_reader: object | None = None  # selffork_orchestrator.usage.ProactiveUsageReader
    launchd_scheduler: object | None = None  # selffork_orchestrator.resume.cron.LaunchdScheduler
    resume_store: object | None = None  # selffork_orchestrator.resume.store.ScheduledResumeStore
    # Telegram bridge for the ``notify_telegram`` act tool. ``None`` (or a
    # :class:`NullTelegramBridge`) when Telegram is disabled / no bot token;
    # the tool then records intent instead of delivering. Typed ``object``
    # here to keep the tools package free of a hard telegram import.
    telegram_bridge: object | None = None  # selffork_orchestrator.telegram.bridge.TelegramBridge
    # M5 Body pillar — vision-driven UI control (ADR-005 §M5-G). Optional, None
    # when the body pillar isn't wired into this session (e.g. legacy text-only
    # round-loop). Tools that require these fields (body_click, body_screenshot,
    # ...) return an "unauthorized" :class:`ToolResult` rather than raise.
    # selffork_body.drivers protocol (web/android/ios/desktop/tmux)
    body_driver: object | None = None
    vision_runtime: object | None = None  # selffork_orchestrator.runtime.base.MultimodalLLMRuntime
    permission_warden: object | None = None  # selffork_body.sandbox.PermissionWarden
    screenshot_store: object | None = None  # selffork_body.storage.ScreenshotStore
    audit_logger: object | None = None  # selffork_shared.audit.AuditLogger (body.* emit)
    # S6 (ADR-006 §4.6) — Self Jr CLI-router control. Optional, None when the
    # router stores aren't wired (e.g. legacy/orphan run); tools that require
    # them return an "unauthorized" :class:`ToolResult` rather than raise.
    cli_override_store: object | None = None  # selffork_orchestrator.router.CliOverrideStore
    cli_runtime_store: object | None = None  # selffork_orchestrator.router.CliRuntimeStore
    # S-Bridge CORE — pending structured question store for the
    # ``AskUserQuestion`` tool. Optional, ``None`` when the orchestrator
    # didn't wire one (tests, legacy code paths); the tool returns
    # ``{"status": "unwired"}`` in that case so Self Jr learns the
    # capability is absent rather than crashing.
    # selffork_orchestrator.tools.structured_question.PendingStructuredQuestionStore
    structured_question_store: object | None = None
    # S-ToolFleet Faz 0 RAG-over-tools seam — the registry itself, used
    # by the ``tool_search`` handler to look up deferred specs. Optional
    # because a test ``ToolContext`` may carry only the tools it needs;
    # ``tool_search`` returns ``status="unwired"`` when missing.
    tool_registry: object | None = None  # selffork_orchestrator.tools.base.ToolRegistry


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
        handler: Callable[
            [ToolContext, A],
            dict[str, Any] | Awaitable[dict[str, Any]],
        ],
        defer_loading: bool = False,
    ) -> None:
        if not name or " " in name:
            raise ValueError(
                f"tool name {name!r} must be non-empty and contain no spaces",
            )
        self.name = name
        self.description = description
        self.args_model: type[A] = args_model
        # S-ToolFleet Faz 0 RAG-over-tools seam: when ``True``, this
        # spec is OMITTED from the eager catalog Self Jr sees in its
        # system prompt and only surfaces after a ``tool_search`` call
        # retrieves it. Default ``False`` keeps every existing tool
        # eagerly available — opt-in flag, no behaviour change for
        # specs that don't set it.
        self.defer_loading = defer_loading
        # Wrap the typed handler in a BaseModel-typed handler so the
        # registry can store handlers uniformly. Both sync and async
        # handlers are supported — the registry resolves them via
        # ``inspect.isawaitable`` at invoke time.

        def _erased(
            ctx: ToolContext,
            args: BaseModel,
        ) -> dict[str, Any] | Awaitable[dict[str, Any]]:
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

    def catalog(
        self, *, include_deferred: bool = True,
    ) -> list[dict[str, Any]]:
        """Catalog suitable for injecting into Jr's system prompt.

        S-ToolFleet Faz 0: with ``include_deferred=False`` skip specs
        whose ``defer_loading=True`` is set so the eager system-prompt
        catalog stays compact. Deferred tools surface only after a
        ``tool_search`` call retrieves them (RAG-over-tools).
        """
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "args_schema": spec.json_schema(),
            }
            for spec in self._tools.values()
            if include_deferred or not spec.defer_loading
        ]

    def eager_names(self) -> list[str]:
        """Names of tools loaded eagerly into the system prompt.

        S-ToolFleet Faz 0 helper: complement of :meth:`deferred_names`.
        """
        return sorted(
            name for name, spec in self._tools.items()
            if not spec.defer_loading
        )

    def deferred_names(self) -> list[str]:
        """Names of tools that must be retrieved via ``tool_search``."""
        return sorted(
            name for name, spec in self._tools.items() if spec.defer_loading
        )

    def deferred_specs(self) -> list[ToolSpec[Any]]:
        """ToolSpec instances of every deferred tool (RAG corpus side)."""
        return [s for s in self._tools.values() if s.defer_loading]

    def invoke(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        """Validate args + invoke a SYNC handler. Always returns a result —
        never raises (handler exceptions are captured as ``handler_error``).

        For tools that bridge to async I/O (Mind tools), use
        :meth:`invoke_async` instead — calling :meth:`invoke` on an async
        handler returns a ``handler_error`` result with a clear hint.
        """
        spec, args, early = self._validate_call(call)
        if early is not None:
            return early
        assert spec is not None and args is not None  # noqa: S101 — validate_call invariant
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
        if inspect.isawaitable(payload):
            return ToolResult(
                tool=call.tool,
                status="handler_error",
                error=(
                    f"tool {call.tool!r} is async; call ToolRegistry.invoke_async "
                    "(or await it from an async caller)"
                ),
            )
        return ToolResult(tool=call.tool, status="ok", payload=payload)

    async def invoke_async(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        """Async-aware invoke. Awaits awaitable handlers; passes sync
        handlers through unchanged. Use this from async call sites
        (e.g. ``Session._handle_tool_calls``) so Mind tools that bridge
        to ``MindStore.upsert_note`` resolve correctly.
        """
        spec, args, early = self._validate_call(call)
        if early is not None:
            return early
        assert spec is not None and args is not None  # noqa: S101
        try:
            result = spec.handler(ctx, args)
            payload = await result if inspect.isawaitable(result) else result
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

    def _validate_call(
        self,
        call: ToolCall,
    ) -> tuple[ToolSpec[Any] | None, BaseModel | None, ToolResult | None]:
        spec = self._tools.get(call.tool)
        if spec is None:
            return (
                None,
                None,
                ToolResult(
                    tool=call.tool,
                    status="unknown_tool",
                    error=(f"tool {call.tool!r} is not registered; known tools: {self.names()}"),
                ),
            )
        try:
            args = spec.args_model.model_validate(call.args)
        except ValidationError as exc:
            return (
                spec,
                None,
                ToolResult(
                    tool=call.tool,
                    status="invalid_args",
                    error=str(exc),
                ),
            )
        return spec, args, None


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
