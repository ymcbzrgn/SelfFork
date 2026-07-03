"""Tests for the S-Train T2 corpus assembler.

Synthetic session events only -- no ``selffork-shared`` import, no GPU. Covers
multi-session flattening, one-sample-per-operator-turn with a full prefix,
source-precedence ordering (Operator_Locked_Decisions section 4), stable order
within a source, empty/opless sessions, and JSONL serialization.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from selffork_reflex.data import (
    SYSTEM_PROMPT,
    TARGET_OPERATOR_WEIGHT,
    CorpusSample,
    SessionCapture,
    SessionEvent,
    assemble_corpus,
    corpus_to_jsonl,
    sample_to_dict,
    source_rank,
    write_corpus,
)


def _op(text: str) -> SessionEvent:
    return SessionEvent(category="selffork_jr.reply", payload={"text": text})


def _tool(tool: str) -> SessionEvent:
    # No ``args`` key -> normalizer content is the bare tool name (see
    # normalize._content_for: with args present it renders "<tool> <args>").
    return SessionEvent(category="tool.call", payload={"tool": tool})


def _agent() -> SessionEvent:
    return SessionEvent(category="agent.invoke", payload={"binary": "/x/claude"})


def _capture(session_id: str, source: str, *events: SessionEvent) -> SessionCapture:
    return SessionCapture(session_id=session_id, source=source, events=list(events))


def test_single_session_one_sample_per_operator_turn() -> None:
    cap = _capture("s1", "self_audit", _op("first"), _agent(), _tool("Read"), _op("second"))
    corpus = assemble_corpus([cap])
    assert len(corpus) == 2
    # Each sample targets one operator turn, full prefix retained.
    first, second = corpus
    assert first.sample.messages[0].content == SYSTEM_PROMPT
    assert first.sample.messages[-1].content == "first"
    assert first.sample.messages[-1].loss_weight == TARGET_OPERATOR_WEIGHT
    # Second sample's prefix grows to include the intervening agent/tool events.
    # Agent payload has no text key -> content falls back to the category;
    # tool payload has no args -> content is the bare tool name.
    assert second.sample.messages[-1].content == "second"
    assert [m.content for m in second.sample.messages] == [
        SYSTEM_PROMPT,
        "first",
        "agent.invoke",
        "Read",
        "second",
    ]


def test_multi_session_flatten_counts_all_operator_turns() -> None:
    caps = [
        _capture("s1", "self_audit", _op("a"), _op("b")),
        _capture("s2", "self_audit", _op("c")),
    ]
    corpus = assemble_corpus(caps)
    assert len(corpus) == 3
    assert [cs.sample.session_id for cs in corpus] == ["s1", "s1", "s2"]


def test_source_precedence_orders_higher_rank_first() -> None:
    caps = [
        _capture("low", "self_audit", _op("x")),
        _capture("high", "claude_code", _op("y")),
    ]
    corpus = assemble_corpus(caps)
    # claude_code (rank 0) precedes self_audit (rank 5) despite input order.
    assert [cs.source for cs in corpus] == ["claude_code", "self_audit"]


def test_sort_is_stable_within_a_source() -> None:
    caps = [
        _capture("s1", "self_audit", _op("one")),
        _capture("s2", "self_audit", _op("two")),
        _capture("s3", "self_audit", _op("three")),
    ]
    corpus = assemble_corpus(caps)
    assert [cs.sample.session_id for cs in corpus] == ["s1", "s2", "s3"]


def test_unknown_source_sorts_last() -> None:
    assert source_rank("claude_code") < source_rank("self_audit")
    assert source_rank("totally_unknown") > source_rank("self_audit")
    caps = [
        _capture("u", "mystery_source", _op("x")),
        _capture("k", "opencode", _op("y")),
    ]
    corpus = assemble_corpus(caps)
    assert [cs.source for cs in corpus] == ["opencode", "mystery_source"]


def test_session_without_operator_turns_contributes_nothing() -> None:
    caps = [
        _capture("empty", "self_audit", _agent(), _tool("Read")),
        _capture("real", "self_audit", _op("hi")),
    ]
    corpus = assemble_corpus(caps)
    assert len(corpus) == 1
    assert corpus[0].sample.session_id == "real"


def test_sample_to_dict_schema() -> None:
    cap = _capture("s1", "self_audit", _op("hello"))
    cs = assemble_corpus([cap])[0]
    row: dict[str, Any] = sample_to_dict(cs)
    assert set(row) == {"session_id", "source", "target_index", "messages"}
    assert row["session_id"] == "s1"
    assert row["source"] == "self_audit"
    assert row["target_index"] == len(row["messages"]) - 1
    assert row["messages"][-1] == {
        "role": "operator",
        "content": "hello",
        "loss_weight": TARGET_OPERATOR_WEIGHT,
    }


def test_corpus_to_jsonl_roundtrips() -> None:
    caps = [
        _capture("s1", "self_audit", _op("a")),
        _capture("s2", "opencode", _op("b")),
    ]
    corpus = assemble_corpus(caps)
    text = corpus_to_jsonl(corpus)
    rows = [json.loads(line) for line in text.splitlines()]
    assert len(rows) == 2
    # opencode outranks self_audit -> serialized first.
    assert rows[0]["source"] == "opencode"


def test_write_corpus_writes_file_and_returns_count(tmp_path: Path) -> None:
    caps = [_capture("s1", "self_audit", _op("a"), _op("b"))]
    corpus = assemble_corpus(caps)
    out = tmp_path / "nested" / "corpus.jsonl"
    count = write_corpus(corpus, out)
    assert count == 2
    assert out.is_file()
    assert len(out.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_corpus_sample_carries_source_attribution() -> None:
    cs = assemble_corpus([_capture("s1", "opencode", _op("x"))])[0]
    assert isinstance(cs, CorpusSample)
    assert cs.source == "opencode"
