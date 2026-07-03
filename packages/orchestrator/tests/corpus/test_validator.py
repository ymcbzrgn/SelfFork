"""Tests for the tool-mastery corpus validation gate.

Runs against the REAL 289-tool registry -- proving the gate accepts a correct
SelfFork tool call and rejects the exact mistakes a small model (or a fallible
teacher) makes: unknown tool, missing/typed-wrong args, empty target, bad
LegalAction. This is the guarantee that only runtime-valid calls enter the
corpus.
"""

from __future__ import annotations

from selffork_orchestrator.corpus import (
    LEGAL_ACTION_LABELS,
    default_registry,
    validate_legal_action,
    validate_reply,
    validate_tool_call,
)

_GOOD_BLOCK = (
    "<selffork-tool-call>\n"
    '{"tool": "kanban_card_move", "args": {"card_id": "card-8f2a", '
    '"to_column": "done"}}\n'
    "</selffork-tool-call>"
)


def test_registry_has_full_fleet() -> None:
    reg = default_registry()
    assert len(list(reg.names())) == 289


# ---- validate_tool_call ---------------------------------------------------
def test_valid_tool_call_passes() -> None:
    errors = validate_tool_call(
        "kanban_card_move", {"card_id": "card-8f2a", "to_column": "done"}
    )
    assert errors == []


def test_unknown_tool_rejected() -> None:
    errors = validate_tool_call("kanban_card_teleport", {"card_id": "x"})
    assert errors
    assert "unknown tool" in errors[0]


def test_missing_required_arg_rejected() -> None:
    # ``to_column`` is required -> pydantic flags it.
    errors = validate_tool_call("kanban_card_move", {"card_id": "card-8f2a"})
    assert errors
    assert any("to_column" in e for e in errors)


def test_unknown_arg_rejected() -> None:
    # Even when the tool tolerates extras at runtime, the corpus gate's
    # strict_args flags a non-canonical (hallucinated) arg.
    errors = validate_tool_call(
        "kanban_card_move",
        {"card_id": "c", "to_column": "done", "hallucinated": True},
    )
    assert errors
    assert any("unknown arg" in e for e in errors)


def test_unknown_arg_allowed_when_strict_off() -> None:
    # strict_args=False falls back to pure runtime fidelity (pydantic only).
    errors = validate_tool_call(
        "kanban_card_move",
        {"card_id": "c", "to_column": "done", "hallucinated": True},
        strict_args=False,
    )
    assert errors == []


# ---- validate_reply -------------------------------------------------------
def test_reply_with_valid_block_ok() -> None:
    result = validate_reply(_GOOD_BLOCK)
    assert result.ok, result.all_errors()
    assert len(result.calls) == 1
    assert result.calls[0].tool == "kanban_card_move"


def test_reply_with_unknown_tool_not_ok() -> None:
    bad = _GOOD_BLOCK.replace("kanban_card_move", "kanban_card_yeet")
    result = validate_reply(bad)
    assert not result.ok
    assert any("unknown tool" in e for e in result.all_errors())


def test_reply_without_block_flagged() -> None:
    result = validate_reply("just some prose, no tool call here")
    assert not result.ok
    assert any("no parseable" in e for e in result.errors)


def test_reply_without_block_allowed_when_not_required() -> None:
    result = validate_reply("prose only", require_tool_call=False)
    assert result.ok


def test_reply_with_two_blocks_validates_each() -> None:
    two = _GOOD_BLOCK + "\n" + _GOOD_BLOCK.replace("card-8f2a", "card-9c3b")
    result = validate_reply(two)
    assert result.ok, result.all_errors()
    assert len(result.calls) == 2


# ---- validate_legal_action ------------------------------------------------
def test_legal_action_labels_are_the_ten() -> None:
    assert len(LEGAL_ACTION_LABELS) == 10
    assert "uzvunu_kullan" in LEGAL_ACTION_LABELS
    assert "kendini_durdur" in LEGAL_ACTION_LABELS


def test_valid_legal_action_passes() -> None:
    assert validate_legal_action("uzvunu_kullan") == []


def test_invalid_legal_action_rejected() -> None:
    errors = validate_legal_action("uzvunu_yok_et")
    assert errors
    assert "unknown LegalAction" in errors[0]
