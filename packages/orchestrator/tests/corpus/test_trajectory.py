"""Tests for the agentic multi-tool trajectory builder.

A trajectory emits one gated training sample per step over a growing prefix,
teaching the model to chain tools (act -> observe -> act). Each sample must also
satisfy the reflex loss-mask (exactly one target at 1.0, priors 0.3, rest 0.0).
"""

from __future__ import annotations

from typing import Any, cast

from selffork_orchestrator.corpus.authored import ALL_TRAJECTORIES
from selffork_orchestrator.corpus.builder import (
    AgenticStep,
    AgenticTrajectory,
    build_trajectories,
    trajectory_stats,
)
from selffork_reflex.data import validate_corpus_rows


def _messages(row: dict[str, object]) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", row["messages"])


def test_demo_trajectories_valid_and_one_sample_per_step() -> None:
    res = build_trajectories(ALL_TRAJECTORIES)
    assert res.ok, res.rejected
    assert len(res.rows) == trajectory_stats(ALL_TRAJECTORIES)["samples"]


def test_trajectory_rows_pass_reflex_t5() -> None:
    res = build_trajectories(ALL_TRAJECTORIES)
    assert validate_corpus_rows(res.rows).ok


def test_trajectory_growing_prefix_and_loss_mask() -> None:
    traj = AgenticTrajectory(
        name="t",
        goal="[görev] test",
        steps=[
            AgenticStep(tool="android_a11y_tree", args={}, result="[sonuç] ağaç"),
            AgenticStep(
                tool="android_click", args={"x": 10, "y": 20}, result="[sonuç] odak"
            ),
            AgenticStep(tool="android_type", args={"text": "hi"}, result="[sonuç] yazıldı"),
        ],
    )
    res = build_trajectories([traj])
    assert res.ok
    assert len(res.rows) == 3
    # step 0: [system, goal, target] = 3 msgs; step 2 grows to 7.
    assert len(_messages(res.rows[0])) == 3
    assert len(_messages(res.rows[2])) == 7
    for row in res.rows:
        msgs = _messages(row)
        assert msgs[-1]["loss_weight"] == 1.0
        assert sum(1 for m in msgs if m["loss_weight"] == 1.0) == 1


def test_bad_step_rejects_whole_trajectory() -> None:
    traj = AgenticTrajectory(
        name="bad",
        goal="g",
        steps=[
            AgenticStep(tool="android_a11y_tree", args={}, result="ok"),
            AgenticStep(tool="android_click", args={"x": 1}, result="ok"),  # no y
        ],
    )
    res = build_trajectories([traj])
    assert not res.ok
    assert res.rows == []
