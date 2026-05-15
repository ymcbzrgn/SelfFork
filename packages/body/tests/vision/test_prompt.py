"""build_prompt + parse_decision — vision pipeline I/O contracts."""

from __future__ import annotations

import json

import pytest

from selffork_body.vision import build_prompt, parse_decision

# ---- build_prompt ----


def test_tier1_renders_goal() -> None:
    out = build_prompt(tier=1, goal="click the Submit button")
    assert "click the Submit button" in out
    assert "JSON" in out


def test_tier2_requires_ax_tree() -> None:
    with pytest.raises(ValueError):
        build_prompt(tier=2, goal="x")


def test_tier2_includes_ax_tree_and_prev_confidence() -> None:
    out = build_prompt(
        tier=2, goal="x", ax_tree_text="<button label='Submit'>", prev_confidence=0.42
    )
    assert "<button label='Submit'>" in out
    assert "0.42" in out


def test_tier3_requires_marks() -> None:
    with pytest.raises(ValueError):
        build_prompt(tier=3, goal="x", ax_tree_text="(empty)")


def test_tier3_renders_marks_summary() -> None:
    out = build_prompt(
        tier=3,
        goal="x",
        ax_tree_text="(empty)",
        prev_confidence=0.3,
        marks_summary="0=login, 1=password, 2=submit",
    )
    assert "Set-of-Marks" in out
    assert "0=login" in out


# ---- parse_decision ----


def test_parse_decision_strips_fences() -> None:
    payload = {
        "action": "click",
        "target": "Submit",
        "bbox": [10, 20, 30, 40],
        "args": {},
        "confidence": 0.92,
        "reason": "found the button",
    }
    raw = "```json\n" + json.dumps(payload) + "\n```"
    decision = parse_decision(raw)
    assert decision["action"] == "click"
    assert decision["confidence"] == 0.92


def test_parse_decision_invalid_json_raises() -> None:
    with pytest.raises(ValueError):
        parse_decision("not json at all")


def test_parse_decision_missing_keys_raises() -> None:
    with pytest.raises(ValueError):
        parse_decision('{"action": "click"}')


def test_parse_decision_top_level_array_raises() -> None:
    with pytest.raises(ValueError):
        parse_decision("[]")
