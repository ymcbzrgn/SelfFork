"""Tests for the tool-mastery corpus builder + the first authored slice.

Proves the end-to-end authoring loop: teacher-authored scenarios render to
canonical targets, pass BOTH the tool-call gate (real registry) AND the reflex
corpus validator (schema + loss mask), and that a deliberately bad scenario is
rejected before it can become a row.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.authored import ALL_SCENARIOS
from selffork_orchestrator.corpus.builder import (
    ToolScenario,
    build_corpus,
    corpus_stats,
)
from selffork_orchestrator.corpus.render import render_target, render_tool_call
from selffork_orchestrator.tools.parser import parse_tool_calls
from selffork_reflex.data import validate_corpus_rows


def test_authored_slice_all_valid() -> None:
    result = build_corpus(ALL_SCENARIOS)
    assert result.ok, result.rejected
    assert len(result.rows) == len(ALL_SCENARIOS)


def test_authored_rows_pass_reflex_corpus_validator() -> None:
    # Every gated row also satisfies the pure corpus schema + loss-mask (T5).
    result = build_corpus(ALL_SCENARIOS)
    report = validate_corpus_rows(result.rows)
    assert report.ok, report.errors


def test_render_roundtrips_through_real_parser() -> None:
    block = render_tool_call(
        "kanban_card_move", {"card_id": "c-1", "to_column": "done"}
    )
    calls = parse_tool_calls(block)
    assert len(calls) == 1
    assert calls[0].tool == "kanban_card_move"
    assert calls[0].args == {"card_id": "c-1", "to_column": "done"}


def test_lean_target_is_bare_block() -> None:
    target = render_target(
        "kanban_card_move", {"card_id": "c", "to_column": "done"}, reasoning=None
    )
    assert target.startswith("<selffork-tool-call>")


def test_reasoning_target_prefixes_reasoning() -> None:
    target = render_target(
        "kanban_card_move",
        {"card_id": "c", "to_column": "done"},
        reasoning="Onaylandı, done'a alıyorum.",
    )
    assert target.startswith("Onaylandı")
    assert "<selffork-tool-call>" in target


def test_gate_rejects_bad_enum_scenario() -> None:
    bad = [
        ToolScenario(
            tool="kanban_card_move",
            archetype="bad_enum",
            context="belirsiz",
            args={"card_id": "c", "to_column": "completed"},  # not in enum
        )
    ]
    result = build_corpus(bad)
    assert not result.ok
    assert result.rows == []


def test_gate_rejects_unknown_tool_scenario() -> None:
    bad = [
        ToolScenario(
            tool="kanban_card_teleport",
            archetype="bad_tool",
            context="x",
            args={"card_id": "c"},
        )
    ]
    result = build_corpus(bad)
    assert not result.ok


def test_first_slice_has_mixed_targets_one_tool() -> None:
    stats = corpus_stats(ALL_SCENARIOS)
    assert stats["tools"] == 1  # first slice is one tool
    assert stats["lean"] >= 1
    assert stats["with_reasoning"] >= 1
    assert stats["scenarios"] == len(ALL_SCENARIOS)
