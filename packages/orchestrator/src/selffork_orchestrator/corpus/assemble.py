"""Assemble the full tool-mastery corpus into one training JSONL artifact.

Combines the three layers -- the mechanical backbone (format/name/args drill),
the single-call reasoning banks (judgement), and the agentic trajectories
(act -> observe -> act chains) -- into one newline-delimited JSON file ready for
the M7 fine-tune. EVERY row was gated against the real tool registry and the
reflex loss-mask before it got here, so nothing the live system would reject
reaches the artifact.

Run as a tool::

    uv run python -m selffork_orchestrator.corpus.assemble --out corpus.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from selffork_orchestrator.corpus.authored import ALL_SCENARIOS, ALL_TRAJECTORIES
from selffork_orchestrator.corpus.builder import (
    Row,
    build_corpus,
    build_trajectories,
    trajectory_stats,
)
from selffork_orchestrator.corpus.mechanical import mechanical_scenarios
from selffork_orchestrator.corpus.validator import default_registry
from selffork_orchestrator.tools import ToolRegistry
from selffork_reflex.data import validate_corpus_rows

__all__ = [
    "DEFAULT_OUT",
    "assemble_corpus_rows",
    "assembly_stats",
    "write_corpus_jsonl",
]

DEFAULT_OUT = Path("~/.selffork/reflex/corpus/tool_mastery_corpus.jsonl").expanduser()


def assemble_corpus_rows(*, registry: ToolRegistry | None = None) -> list[Row]:
    """Build every gated row (mechanical + reasoning + agentic) in one list.

    Raises ``ValueError`` if any authored item fails the gate -- that would be a
    corpus regression, not an expected outcome (the banks are authored-clean).
    """
    reg = registry if registry is not None else default_registry()
    mechanical = mechanical_scenarios(registry=reg)
    single = build_corpus([*mechanical, *ALL_SCENARIOS], registry=reg)
    trajectories = build_trajectories(ALL_TRAJECTORIES, registry=reg)
    if single.rejected or trajectories.rejected:
        raise ValueError(
            f"corpus regression: {len(single.rejected)} single-call + "
            f"{len(trajectories.rejected)} trajectory rejections at assembly"
        )
    return [*single.rows, *trajectories.rows]


def assembly_stats(*, registry: ToolRegistry | None = None) -> dict[str, int]:
    """Counts for a build report (mechanical / reasoning / agentic / tools)."""
    reg = registry if registry is not None else default_registry()
    mechanical = mechanical_scenarios(registry=reg)
    tools_covered = (
        {s.tool for s in mechanical}
        | {s.tool for s in ALL_SCENARIOS}
        | {st.tool for t in ALL_TRAJECTORIES for st in t.steps}
    )
    traj_samples = trajectory_stats(ALL_TRAJECTORIES)["samples"]
    return {
        "mechanical": len(mechanical),
        "reasoning_single": len(ALL_SCENARIOS),
        "agentic_samples": traj_samples,
        "trajectories": len(ALL_TRAJECTORIES),
        "total": len(mechanical) + len(ALL_SCENARIOS) + traj_samples,
        "tools_covered": len(tools_covered),
    }


def write_corpus_jsonl(
    path: str | Path, *, registry: ToolRegistry | None = None
) -> dict[str, int]:
    """Assemble, validate (reflex loss-mask), and write the JSONL artifact.

    Returns the assembly stats plus the written row count. Refuses to write a
    corpus that fails the reflex validator.
    """
    reg = registry if registry is not None else default_registry()
    rows = assemble_corpus_rows(registry=reg)
    report = validate_corpus_rows(rows)
    if not report.ok:
        raise ValueError(f"corpus failed reflex validation: {report.errors[:5]}")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    stats = assembly_stats(registry=reg)
    stats["written"] = len(rows)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assemble the SelfFork tool-mastery corpus into a JSONL artifact."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"output JSONL path (default: {DEFAULT_OUT})",
    )
    ns = parser.parse_args(argv)
    try:
        stats = write_corpus_jsonl(ns.out)
    except ValueError as exc:
        print(f"corpus build FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {stats['written']} samples to {ns.out}")
    print(
        f"  mechanical={stats['mechanical']} "
        f"reasoning={stats['reasoning_single']} "
        f"agentic={stats['agentic_samples']} "
        f"({stats['trajectories']} trajectories)"
    )
    print(f"  tools covered: {stats['tools_covered']} / 289")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
