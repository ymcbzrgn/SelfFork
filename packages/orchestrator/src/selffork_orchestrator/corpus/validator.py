"""Tool-call correctness gate for the synthetic tool-mastery corpus.

Every synthetic training target that emits a ``<selffork-tool-call>`` is
validated against the REAL tool registry: the tool name must exist and its args
must pass the tool's own pydantic ``args_model`` -- the exact check the runtime
runs (:func:`selffork_orchestrator.tools.parser.parse_tool_calls` +
``ToolRegistry``). LegalAction labels are checked against the closed heartbeat
enum. A target that does not round-trip is REJECTED before it can poison the
corpus -- the linchpin that lets a tiny fine-tuned model reach high tool-call
accuracy: it never trains on a call the live system would refuse.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from selffork_orchestrator.heartbeat.actions import LegalAction
from selffork_orchestrator.tools import ToolRegistry, build_default_registry
from selffork_orchestrator.tools.parser import parse_tool_calls

__all__ = [
    "LEGAL_ACTION_LABELS",
    "ReplyValidation",
    "ToolCallCheck",
    "default_registry",
    "validate_legal_action",
    "validate_reply",
    "validate_tool_call",
]

# The 10 closed outer-loop action labels (heartbeat/actions.py::LegalAction).
LEGAL_ACTION_LABELS: frozenset[str] = frozenset(action.value for action in LegalAction)

_REGISTRY: ToolRegistry | None = None


def default_registry() -> ToolRegistry:
    """Return a cached default registry (289 tools); built once, reused."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_default_registry()
    return _REGISTRY


@dataclass(frozen=True)
class ToolCallCheck:
    """Validation outcome for one ``<selffork-tool-call>`` block."""

    tool: str
    args: dict[str, object]
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class ReplyValidation:
    """Validation outcome for one Jr reply (which may hold 0+ tool calls)."""

    calls: list[ToolCallCheck]
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and all(check.ok for check in self.calls)

    def all_errors(self) -> list[str]:
        """Flatten reply-level + per-call errors for a single report line."""
        out = list(self.errors)
        for check in self.calls:
            out.extend(check.errors)
        return out


def validate_tool_call(
    tool: str,
    args: dict[str, object],
    *,
    registry: ToolRegistry | None = None,
    strict_args: bool = True,
) -> list[str]:
    """Validate one tool call against the real registry + ``args_model``.

    Returns human-readable errors (empty == valid). The pydantic
    ``args_model.model_validate`` mirrors exactly what the runtime does before
    dispatching a call, so a passing call is one the live system would accept.

    ``strict_args`` (default on for corpus use) additionally rejects any
    top-level arg not declared in the tool's schema -- STRICTER than the
    runtime, because some tools tolerate extra args but a fine-tune corpus must
    be canonical (a tiny model memorizes junk args it is shown).
    """
    reg = registry if registry is not None else default_registry()
    spec = reg.get(tool)
    if spec is None:
        return [f"unknown tool {tool!r} (not in the 289-tool registry)"]
    errors: list[str] = []
    try:
        spec.args_model.model_validate(args)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"]) or "<root>"
            errors.append(f"{tool}.args.{loc}: {err['msg']}")
    # Canonical-args check only when pydantic was happy (else the extra key is
    # already reported by an ``extra=forbid`` model -- avoid double-reporting).
    if not errors and strict_args:
        properties = spec.json_schema().get("properties") or {}
        known = set(properties)
        for key in args:
            if key not in known:
                errors.append(
                    f"{tool}.args.{key}: unknown arg (not in schema; corpus "
                    "requires canonical args only)"
                )
    return errors


def validate_reply(
    reply: str,
    *,
    registry: ToolRegistry | None = None,
    require_tool_call: bool = True,
) -> ReplyValidation:
    """Parse + validate every ``<selffork-tool-call>`` block in a reply.

    ``require_tool_call`` flags a target that emits no parseable block (a common
    synthetic-authoring slip -- e.g. a mistyped tag) as an error.
    """
    reg = registry if registry is not None else default_registry()
    parsed = parse_tool_calls(reply)
    errors: list[str] = []
    if require_tool_call and not parsed:
        errors.append("reply has no parseable <selffork-tool-call> block")
    checks = [
        ToolCallCheck(
            tool=call.tool,
            args=dict(call.args),
            errors=validate_tool_call(call.tool, dict(call.args), registry=reg),
        )
        for call in parsed
    ]
    return ReplyValidation(calls=checks, errors=errors)


def validate_legal_action(label: str) -> list[str]:
    """Check a LegalAction label against the closed 10-label heartbeat enum."""
    if label not in LEGAL_ACTION_LABELS:
        return [f"unknown LegalAction {label!r} (not one of the 10 closed labels)"]
    return []
