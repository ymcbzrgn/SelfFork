"""Tests for :mod:`selffork_mind.projections.provenance`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from selffork_mind.projections.provenance import (
    ProvenanceEntry,
    ProvenanceRecorder,
)


@pytest.mark.anyio
async def test_record_and_read_round_trip(tmp_path: Path) -> None:
    log = tmp_path / "provenance.jsonl"
    rec = ProvenanceRecorder(log_path=log)
    entry = ProvenanceEntry(
        correlation_id="01HJTESTCORR",
        session_id="01HJSESS",
        project_slug="selffork",
        query="hangi embedder?",
        note_ids=(uuid4(), uuid4()),
        scores=(0.91, 0.87),
        retriever="vector:bge-m3",
        reranker="bge-rerank-v2-m3",
    )
    await rec.record(entry)

    rows = rec.read_all()
    assert len(rows) == 1
    out = rows[0]
    assert out.correlation_id == "01HJTESTCORR"
    assert out.query == "hangi embedder?"
    assert out.retriever == "vector:bge-m3"
    assert out.reranker == "bge-rerank-v2-m3"
    assert out.note_ids == entry.note_ids
    assert out.scores == entry.scores


@pytest.mark.anyio
async def test_record_many_appends_in_order(tmp_path: Path) -> None:
    log = tmp_path / "provenance.jsonl"
    rec = ProvenanceRecorder(log_path=log)
    entries = [
        ProvenanceEntry(
            correlation_id=f"corr-{i}",
            session_id="s",
            project_slug=None,
            query=f"q{i}",
            note_ids=(),
            scores=(),
            retriever="vector:bge-m3",
            ts=datetime(2026, 5, 7, 0, 0, i, tzinfo=UTC),
        )
        for i in range(5)
    ]
    await rec.record_many(entries)
    rows = rec.read_all()
    assert [r.correlation_id for r in rows] == [
        "corr-0",
        "corr-1",
        "corr-2",
        "corr-3",
        "corr-4",
    ]


@pytest.mark.anyio
async def test_malformed_lines_are_skipped(tmp_path: Path) -> None:
    log = tmp_path / "provenance.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("not-json\n", encoding="utf-8")
    rec = ProvenanceRecorder(log_path=log)
    valid = ProvenanceEntry(
        correlation_id="ok",
        session_id="s",
        project_slug=None,
        query="q",
        note_ids=(),
        scores=(),
        retriever="vector:bge-m3",
    )
    await rec.record(valid)

    rows = rec.read_all()
    assert len(rows) == 1
    assert rows[0].correlation_id == "ok"


def test_read_all_missing_file_returns_empty(tmp_path: Path) -> None:
    rec = ProvenanceRecorder(log_path=tmp_path / "does-not-exist.jsonl")
    assert rec.read_all() == []
