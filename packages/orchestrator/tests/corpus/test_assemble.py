"""Tests for the full-corpus JSONL assembler."""

from __future__ import annotations

import json
from pathlib import Path

from selffork_orchestrator.corpus.assemble import (
    assemble_corpus_rows,
    assembly_stats,
    write_corpus_jsonl,
)
from selffork_reflex.data import validate_corpus_rows


def test_assemble_rows_match_stats_and_pass_t5() -> None:
    rows = assemble_corpus_rows()
    stats = assembly_stats()
    assert len(rows) == stats["total"]
    assert stats["tools_covered"] == 289
    assert validate_corpus_rows(rows).ok


def test_write_corpus_jsonl_roundtrips(tmp_path: Path) -> None:
    out = tmp_path / "corpus" / "tool_mastery.jsonl"
    stats = write_corpus_jsonl(out)
    assert out.is_file()
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == stats["written"] == stats["total"]
    # every line is a valid corpus row with the expected shape
    for line in lines:
        row = json.loads(line)
        assert set(row) >= {"source", "session_id", "target_index", "messages"}
        assert row["messages"][row["target_index"]]["loss_weight"] == 1.0


def test_assembly_stats_layers() -> None:
    stats = assembly_stats()
    assert stats["mechanical"] > 0
    assert stats["reasoning_single"] > 0
    assert stats["agentic_samples"] > 0
    assert stats["total"] == (
        stats["mechanical"] + stats["reasoning_single"] + stats["agentic_samples"]
    )
