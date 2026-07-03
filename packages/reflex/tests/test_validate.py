"""Tests for the S-Train T5 corpus validator.

Builds a valid corpus through the real T2 assembler, then asserts the validator
accepts it and rejects each corruption mode the S-Train smoke gate names (bad
loss mask, missing/unknown source, schema drift). Also checks the advisory
agentic-trace-length flag (ADR-010 section 2.3). No model, no I/O beyond tmp.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from selffork_reflex.data import (
    AGENTIC_TRACE_TOOL_TARGET,
    PRIOR_OPERATOR_WEIGHT,
    SessionCapture,
    SessionEvent,
    assemble_corpus,
    sample_to_dict,
    validate_corpus_file,
    validate_corpus_rows,
    write_corpus,
)


def _op(text: str) -> SessionEvent:
    return SessionEvent(category="selffork_jr.reply", payload={"text": text})


def _tool(tool: str = "Read") -> SessionEvent:
    return SessionEvent(category="tool.call", payload={"tool": tool, "args": {}})


def _valid_rows() -> list[dict[str, Any]]:
    caps = [
        SessionCapture("s1", "self_audit", [_op("a"), _tool(), _op("b")]),
        SessionCapture("s2", "opencode", [_op("c")]),
    ]
    return [sample_to_dict(cs) for cs in assemble_corpus(caps)]


# ---- happy path -----------------------------------------------------------
def test_valid_corpus_passes() -> None:
    report = validate_corpus_rows(_valid_rows())
    assert report.ok, report.errors
    assert report.errors == []
    assert report.sample_count == 3


# ---- loss-mask corruption -------------------------------------------------
def test_rejects_bad_target_weight() -> None:
    rows = _valid_rows()
    rows[0]["messages"][-1]["loss_weight"] = 0.5  # target must be 1.0
    report = validate_corpus_rows(rows)
    assert not report.ok
    assert any("loss_weight" in e for e in report.errors)


def test_rejects_prior_operator_weight_drift() -> None:
    # A session with a prior operator turn (weight 0.3) then a target turn.
    caps = [SessionCapture("s1", "self_audit", [_op("prior"), _op("target")])]
    rows: list[dict[str, Any]] = [sample_to_dict(cs) for cs in assemble_corpus(caps)]
    # The 2nd sample has a prior operator message at index 1 (weight 0.3).
    assert rows[1]["messages"][1]["loss_weight"] == PRIOR_OPERATOR_WEIGHT
    rows[1]["messages"][1]["loss_weight"] = 0.0
    report = validate_corpus_rows(rows)
    assert not report.ok
    assert any("loss_weight" in e for e in report.errors)


def test_rejects_two_target_weights() -> None:
    rows = _valid_rows()
    # Stamp a non-target message with the target weight -> two 1.0s.
    rows[0]["messages"][0]["loss_weight"] = 1.0
    report = validate_corpus_rows(rows)
    assert not report.ok
    assert any("exactly one target" in e for e in report.errors)


# ---- source attribution ---------------------------------------------------
def test_rejects_missing_source() -> None:
    rows = _valid_rows()
    del rows[0]["source"]
    report = validate_corpus_rows(rows)
    assert not report.ok
    assert any("source" in e for e in report.errors)


def test_rejects_unknown_source() -> None:
    rows = _valid_rows()
    rows[0]["source"] = "myspace_export"
    report = validate_corpus_rows(rows)
    assert not report.ok
    assert any("source" in e for e in report.errors)


# ---- schema drift ---------------------------------------------------------
def test_rejects_missing_messages() -> None:
    rows = _valid_rows()
    del rows[0]["messages"]
    report = validate_corpus_rows(rows)
    assert not report.ok
    assert any("messages" in e for e in report.errors)


def test_rejects_target_index_not_last() -> None:
    rows = _valid_rows()
    rows[0]["target_index"] = 0
    report = validate_corpus_rows(rows)
    assert not report.ok
    assert any("target_index" in e for e in report.errors)


def test_rejects_bad_role() -> None:
    rows = _valid_rows()
    rows[0]["messages"][1]["role"] = "wizard"
    report = validate_corpus_rows(rows)
    assert not report.ok
    assert any("role" in e for e in report.errors)


def test_rejects_non_system_first_message() -> None:
    rows = _valid_rows()
    rows[0]["messages"][0]["role"] = "context"
    report = validate_corpus_rows(rows)
    assert not report.ok
    assert any("system" in e for e in report.errors)


def test_rejects_empty_corpus() -> None:
    report = validate_corpus_rows([])
    assert not report.ok
    assert any("empty" in e for e in report.errors)


# ---- agentic-trace distribution flag -------------------------------------
def test_short_traces_warn_not_error() -> None:
    report = validate_corpus_rows(_valid_rows())
    assert report.ok  # advisory only
    assert report.warnings
    assert any("agentic-trace" in w for w in report.warnings)
    assert report.agentic_trace_target_hits == 0


def test_long_trace_meets_target_no_warning() -> None:
    events: list[SessionEvent] = [_tool(f"T{i}") for i in range(AGENTIC_TRACE_TOOL_TARGET)]
    events.append(_op("finally"))
    rows: list[dict[str, Any]] = [
        sample_to_dict(cs) for cs in assemble_corpus([SessionCapture("big", "self_audit", events)])
    ]
    report = validate_corpus_rows(rows)
    assert report.ok, report.errors
    assert report.agentic_trace_max >= AGENTIC_TRACE_TOOL_TARGET
    assert report.agentic_trace_target_hits == 1
    assert not any("agentic-trace" in w for w in report.warnings)


# ---- file glue ------------------------------------------------------------
def test_validate_corpus_file_roundtrip(tmp_path: Path) -> None:
    corpus = assemble_corpus([SessionCapture("s1", "self_audit", [_op("a"), _op("b")])])
    path = tmp_path / "corpus.jsonl"
    write_corpus(corpus, path)
    report = validate_corpus_file(path)
    assert report.ok, report.errors
    assert report.sample_count == 2


def test_validate_corpus_file_rejects_bad_json(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    path.write_text('{"session_id": "s1"}\n{not valid json\n', encoding="utf-8")
    report = validate_corpus_file(path)
    assert not report.ok
    assert any("invalid JSON" in e for e in report.errors)


def test_validate_corpus_file_missing(tmp_path: Path) -> None:
    report = validate_corpus_file(tmp_path / "nope.jsonl")
    assert not report.ok
    assert any("not found" in e for e in report.errors)
