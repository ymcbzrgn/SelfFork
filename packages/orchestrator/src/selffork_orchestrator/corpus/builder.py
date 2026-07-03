"""Author -> validated corpus-row builder for the tool-mastery corpus.

The teacher (Claude) authors :class:`ToolScenario` objects -- the creative part
(situation, chosen tool, args, optional reasoning). This module renders each to
a reflex corpus row and runs it through the correctness gate
(:mod:`selffork_orchestrator.corpus.validator`). Only rows whose target is a
runtime-valid, canonical tool call survive; the rest are returned as
``rejected`` for the author to fix. Nothing invalid can reach the corpus.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from selffork_orchestrator.corpus.render import render_target
from selffork_orchestrator.corpus.validator import default_registry, validate_reply
from selffork_orchestrator.tools import ToolRegistry
from selffork_reflex.data import SYSTEM_PROMPT

__all__ = [
    "BuildResult",
    "ToolScenario",
    "build_corpus",
    "build_row",
    "corpus_stats",
]

Row = dict[str, object]


@dataclass(frozen=True)
class ToolScenario:
    """One authored training scenario for a single tool call.

    ``reasoning=None`` -> lean target; a short string -> reply-with-reasoning
    (the teacher's judgement per the hybrid mix). ``context`` is the situation
    the model reasons over (loss weight 0); the rendered target is the operator
    turn it must learn (loss weight 1.0).
    """

    tool: str
    archetype: str
    context: str
    args: dict[str, object]
    reasoning: str | None = None
    index: int = 0


@dataclass(frozen=True)
class BuildResult:
    """Outcome of building a batch of scenarios."""

    rows: list[Row]
    rejected: list[tuple[ToolScenario, list[str]]]

    @property
    def ok(self) -> bool:
        return not self.rejected


def _canonical_args(
    tool: str, args: dict[str, object], *, registry: ToolRegistry
) -> dict[str, object]:
    """Reorder args to the tool's schema property order (canonical form)."""
    spec = registry.get(tool)
    if spec is None:
        return dict(args)
    order = list((spec.json_schema().get("properties") or {}).keys())
    ordered: dict[str, object] = {key: args[key] for key in order if key in args}
    for key, value in args.items():
        if key not in ordered:
            ordered[key] = value  # unknown keys kept so the gate can reject them
    return ordered


def build_row(scenario: ToolScenario, *, registry: ToolRegistry) -> Row:
    """Render one scenario to a reflex corpus row (no validation here)."""
    args = _canonical_args(scenario.tool, scenario.args, registry=registry)
    target = render_target(scenario.tool, args, reasoning=scenario.reasoning)
    messages: list[Row] = [
        {"role": "system", "content": SYSTEM_PROMPT, "loss_weight": 0.0},
        {"role": "context", "content": scenario.context, "loss_weight": 0.0},
        {"role": "operator", "content": target, "loss_weight": 1.0},
    ]
    return {
        "source": "synthetic",
        "session_id": f"syn_{scenario.tool}_{scenario.archetype}_{scenario.index:04d}",
        "target_index": len(messages) - 1,
        "messages": messages,
    }


def build_corpus(
    scenarios: Iterable[ToolScenario], *, registry: ToolRegistry | None = None
) -> BuildResult:
    """Render + gate a batch of scenarios; return valid rows + rejections.

    Each scenario's rendered target must pass the tool-call gate (name exists,
    args validate against the real ``args_model``, canonical args). A rejected
    scenario never becomes a row.
    """
    reg = registry if registry is not None else default_registry()
    rows: list[Row] = []
    rejected: list[tuple[ToolScenario, list[str]]] = []
    for scenario in scenarios:
        args = _canonical_args(scenario.tool, scenario.args, registry=reg)
        target = render_target(scenario.tool, args, reasoning=scenario.reasoning)
        result = validate_reply(target, registry=reg)
        if not result.ok:
            rejected.append((scenario, result.all_errors()))
            continue
        rows.append(build_row(scenario, registry=reg))
    return BuildResult(rows=rows, rejected=rejected)


def corpus_stats(scenarios: Sequence[ToolScenario]) -> dict[str, int]:
    """Quick coverage tally: distinct tools, archetypes, lean vs reasoning."""
    return {
        "scenarios": len(scenarios),
        "tools": len({s.tool for s in scenarios}),
        "archetypes": len({s.archetype for s in scenarios}),
        "lean": sum(1 for s in scenarios if s.reasoning is None),
        "with_reasoning": sum(1 for s in scenarios if s.reasoning is not None),
    }
