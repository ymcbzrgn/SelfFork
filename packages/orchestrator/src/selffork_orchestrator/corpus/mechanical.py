"""Programmatic backbone -- the mechanical format/name/args drill.

Generates lean :class:`ToolScenario` objects across the whole fleet from the
spec cards: one canonical call per synthesizable tool, plus an enum-sweep
(one example per valid value) for every enum arg. This drills the exact tool
NAMES, ARG shapes, ENUM values and wire FORMAT that a small model gets wrong at
~20% -- cheaply, deterministically, offline, and every target gate-validated.

Judgement (which tool, when to ask, multi-tool chains) is NOT here; that is the
teacher's (Fable's) authored richness. Backbone = correctness drill; authored =
realism + reasoning. Both pass the same gate.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.builder import ToolScenario
from selffork_orchestrator.corpus.spec_cards import (
    SpecCard,
    extract_spec_cards,
    synthesize_args,
)
from selffork_orchestrator.corpus.validator import default_registry
from selffork_orchestrator.tools import ToolRegistry

__all__ = ["mechanical_scenarios"]


def _mech_context(card: SpecCard, *, hint: str | None = None) -> str:
    desc = (card.description or "").strip().splitlines()[0][:160] if card.description else ""
    base = f"[araç çağrısı] {card.name}: {desc}" if desc else f"[araç çağrısı] {card.name}"
    return f"{base} (arg: {hint})" if hint else base


def mechanical_scenarios(
    cards: list[SpecCard] | None = None, *, registry: ToolRegistry | None = None
) -> list[ToolScenario]:
    """Build the mechanical drill scenarios for every synthesizable tool."""
    reg = registry if registry is not None else default_registry()
    deck = cards if cards is not None else extract_spec_cards(reg)
    out: list[ToolScenario] = []
    for card in deck:
        base = synthesize_args(card, registry=reg)
        if base is None:
            continue  # complex-schema tool -> routed to authored scenarios
        out.append(
            ToolScenario(
                tool=card.name,
                archetype="mech_happy",
                context=_mech_context(card),
                args=dict(base),
                index=0,
            )
        )
        for arg in card.required_args:
            if arg.enum and len(arg.enum) > 1:
                for i, value in enumerate(arg.enum):
                    variant = dict(base)
                    variant[arg.name] = value
                    out.append(
                        ToolScenario(
                            tool=card.name,
                            archetype=f"mech_enum__{arg.name}",
                            context=_mech_context(card, hint=f"{arg.name}={value!r}"),
                            args=variant,
                            index=i,
                        )
                    )
    return out
