"""Spec cards extracted from the real 289-tool registry.

Two consumers:

1. **Grounding for the teacher** (Claude / Fable): a compact, exact card per tool
   -- name, description, eager/deferred, and every arg's type / enum / required
   flag -- so an authored scenario uses only real names + valid enum values. The
   gate (:mod:`selffork_orchestrator.corpus.validator`) is the backstop; the
   card keeps authoring on-contract in the first place.
2. **The programmatic backbone**: :func:`synthesize_args` builds a minimal valid
   args dict for tools with simple required args, so the mechanical
   format/name/args drill can cover the fleet automatically. Tools whose
   required args are complex (nested objects/arrays) return ``None`` and are
   routed to authored (Fable) scenarios instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from selffork_orchestrator.corpus.validator import default_registry, validate_tool_call
from selffork_orchestrator.tools import ToolRegistry

__all__ = [
    "ArgField",
    "SpecCard",
    "extract_spec_cards",
    "synthesize_args",
]


@dataclass(frozen=True)
class ArgField:
    """One tool argument, distilled from the JSON schema."""

    name: str
    json_type: str | None
    required: bool
    enum: tuple[object, ...] | None
    description: str


@dataclass(frozen=True)
class SpecCard:
    """Compact, exact card for one tool -- the authoring palette + backbone input."""

    name: str
    description: str
    deferred: bool
    args: tuple[ArgField, ...]

    @property
    def required_args(self) -> tuple[ArgField, ...]:
        return tuple(arg for arg in self.args if arg.required)


def _arg_fields(schema: dict[str, object]) -> tuple[ArgField, ...]:
    props_obj = schema.get("properties")
    props: dict[str, object] = props_obj if isinstance(props_obj, dict) else {}
    required_obj = schema.get("required")
    required = set(required_obj) if isinstance(required_obj, list) else set()
    fields: list[ArgField] = []
    for name, spec in props.items():
        prop: dict[str, object] = spec if isinstance(spec, dict) else {}
        enum_obj = prop.get("enum")
        enum = tuple(enum_obj) if isinstance(enum_obj, list) else None
        json_type = prop.get("type")
        fields.append(
            ArgField(
                name=name,
                json_type=json_type if isinstance(json_type, str) else None,
                required=name in required,
                enum=enum,
                description=str(prop.get("description") or ""),
            )
        )
    return tuple(fields)


def extract_spec_cards(registry: ToolRegistry | None = None) -> list[SpecCard]:
    """Extract a :class:`SpecCard` for every tool in the registry."""
    reg = registry if registry is not None else default_registry()
    eager = set(reg.eager_names())
    cards: list[SpecCard] = []
    for name in reg.names():
        spec = reg.get(name)
        if spec is None:
            continue
        schema = spec.json_schema()
        cards.append(
            SpecCard(
                name=name,
                description=str(spec.description or ""),
                deferred=name not in eager,
                args=_arg_fields(schema),
            )
        )
    return cards


_TYPE_DEFAULT: dict[str, object] = {
    "string": "example",
    "integer": 1,
    "number": 1.0,
    "boolean": True,
}


def synthesize_args(
    card: SpecCard, *, registry: ToolRegistry | None = None
) -> dict[str, object] | None:
    """Best-effort MINIMAL valid args (required only) for the mechanical drill.

    Returns ``None`` when a required arg cannot be synthesized cheaply (nested
    object/array or an untyped field) -- those tools are routed to authored
    (Fable/manual) scenarios. Any candidate is gate-checked before return, so a
    non-``None`` result is guaranteed runtime-valid + canonical.
    """
    reg = registry if registry is not None else default_registry()
    args: dict[str, object] = {}
    for arg in card.required_args:
        if arg.enum:
            args[arg.name] = arg.enum[0]
        elif arg.json_type in _TYPE_DEFAULT:
            args[arg.name] = _TYPE_DEFAULT[arg.json_type]
        else:
            return None
    if validate_tool_call(card.name, args, registry=reg):
        return None
    return args
