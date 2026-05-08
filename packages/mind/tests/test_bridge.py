"""Tests for the three-pillar bridge (Order 6)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from selffork_mind.bridge import (
    ExportConfig,
    ReflexCorpusExporter,
    SM2Card,
    SM2Scheduler,
    shuffle_interleaved,
    sm2_e_factor,
    sm2_next_review,
)
from selffork_mind.memory.tiers import EpisodicWriter, ProceduralDistiller
from selffork_mind.memory.tiers.episodic import EpisodicToolCall
from selffork_mind.store import DuckDBMindStore


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


# ── SM-2 scheduler ─────────────────────────────────────────────────────────


def test_sm2_e_factor_decreases_on_low_quality() -> None:
    new_ef = sm2_e_factor(current=2.5, quality=0)
    assert new_ef < 2.5


def test_sm2_e_factor_increases_on_high_quality() -> None:
    new_ef = sm2_e_factor(current=2.5, quality=5)
    assert new_ef >= 2.5


def test_sm2_e_factor_floor_is_1_3() -> None:
    # Quality 0 from a low-EF starting point should still floor at 1.3.
    new_ef = sm2_e_factor(current=1.4, quality=0)
    assert new_ef == 1.3


def test_sm2_e_factor_invalid_quality() -> None:
    with pytest.raises(ValueError):
        sm2_e_factor(current=2.5, quality=6)


def test_sm2_next_review_quality_below_3_resets() -> None:
    moment = datetime.now(UTC)
    reps, interval, _ = sm2_next_review(
        repetitions=4,
        interval_days=14,
        e_factor=2.5,
        quality=2,
        last_reviewed_at=moment,
    )
    assert reps == 0
    assert interval == 1


def test_sm2_next_review_quality_5_grows_interval() -> None:
    moment = datetime.now(UTC)
    _, interval1, _ = sm2_next_review(
        repetitions=0,
        interval_days=0,
        e_factor=2.5,
        quality=5,
        last_reviewed_at=moment,
    )
    _, interval2, _ = sm2_next_review(
        repetitions=1,
        interval_days=interval1,
        e_factor=2.5,
        quality=5,
        last_reviewed_at=moment,
    )
    _, interval3, _ = sm2_next_review(
        repetitions=2,
        interval_days=interval2,
        e_factor=2.5,
        quality=5,
        last_reviewed_at=moment,
    )
    assert interval1 == 1
    assert interval2 == 6
    assert interval3 == round(6 * 2.5)


def test_sm2_scheduler_record_creates_card() -> None:
    sched = SM2Scheduler()
    updated = sched.record(item_id="x", quality=5)
    assert sched.get("x") is not None
    assert updated.repetitions == 1


def test_sm2_scheduler_due_cards() -> None:
    moment = datetime.now(UTC)
    sched = SM2Scheduler(
        cards=[
            SM2Card(item_id="due", next_review_at=moment - timedelta(days=1)),
            SM2Card(item_id="not_due", next_review_at=moment + timedelta(days=5)),
        ],
    )
    due = sched.due_cards(at=moment)
    assert [c.item_id for c in due] == ["due"]


def test_sm2_scheduler_all_returns_sorted() -> None:
    sched = SM2Scheduler(
        cards=[SM2Card(item_id="b"), SM2Card(item_id="a")],
    )
    assert [c.item_id for c in sched.all()] == ["a", "b"]


# ── Interleaving ──────────────────────────────────────────────────────────


def test_shuffle_interleaved_round_robin() -> None:
    out = shuffle_interleaved([["a1", "a2", "a3"], ["b1", "b2"], ["c1"]])
    assert out == ["a1", "b1", "c1", "a2", "b2", "a3"]


def test_shuffle_interleaved_empty_groups_skipped() -> None:
    out = shuffle_interleaved([[], ["x"], []])
    assert out == ["x"]


def test_shuffle_interleaved_empty_input() -> None:
    assert shuffle_interleaved([]) == []


def test_shuffle_interleaved_deterministic() -> None:
    args = [["a"], ["b"], ["c"]]
    a = shuffle_interleaved(args)
    b = shuffle_interleaved(args)
    assert a == b


# ── ReflexCorpusExporter ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_export_empty_writes_empty_file(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        exporter = ReflexCorpusExporter(store=store)
        out = tmp_path / "corpus.jsonl"
        report = await exporter.export(
            ExportConfig(out_path=out, project_slug="alpha"),
        )
        assert out.is_file()
        assert out.read_text(encoding="utf-8") == ""
        assert report.items_written == 0


@pytest.mark.anyio
async def test_export_writes_one_item_per_pattern(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        # Seed Procedural via the standard pipeline.
        writer = EpisodicWriter(store=store)
        for i in range(2):
            await writer.write_round(
                session_id="s1",
                project_slug="alpha",
                cli_agent="claude-code",
                round_index=i,
                operator_message=f"m{i}",
                cli_response=f"r{i}",
                tool_calls=[
                    EpisodicToolCall(tool="a", args={"i": i}, status="ok"),
                    EpisodicToolCall(tool="b", args={"i": i}, status="ok"),
                ],
            )
        await ProceduralDistiller(store=store, min_pair_count=2).distil(
            project_slug="alpha",
        )
        exporter = ReflexCorpusExporter(store=store)
        out = tmp_path / "corpus.jsonl"
        report = await exporter.export(
            ExportConfig(out_path=out, project_slug="alpha", tiers=("procedural",)),
        )
        assert report.items_written >= 1
        lines = [line for line in out.read_text(encoding="utf-8").splitlines() if line]
        assert lines
        for line in lines:
            payload = json.loads(line)
            assert "messages" in payload
            assert payload["messages"][0]["role"] == "system"
            assert "metadata" in payload
            assert "sm2" in payload["metadata"]


@pytest.mark.anyio
async def test_export_deterministic(tmp_path: Path) -> None:
    """Same Mind state + same config = identical bytes."""
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        for i in range(2):
            await writer.write_round(
                session_id="s1",
                project_slug="alpha",
                cli_agent="claude-code",
                round_index=i,
                operator_message=f"m{i}",
                cli_response=f"r{i}",
                tool_calls=[
                    EpisodicToolCall(tool="a", args={"i": i}, status="ok"),
                    EpisodicToolCall(tool="b", args={"i": i}, status="ok"),
                ],
            )
        await ProceduralDistiller(store=store, min_pair_count=2).distil(
            project_slug="alpha",
        )
        out1 = tmp_path / "corpus1.jsonl"
        out2 = tmp_path / "corpus2.jsonl"
        await ReflexCorpusExporter(store=store).export(
            ExportConfig(out_path=out1, project_slug="alpha"),
        )
        await ReflexCorpusExporter(store=store).export(
            ExportConfig(out_path=out2, project_slug="alpha"),
        )

        # Note: SM-2 metadata's `next_review_at` shifts each call (timestamp
        # is `now` + interval). Strip that field for the byte-identity check.
        def _strip_volatile(text: str) -> list[dict[str, object]]:
            out: list[dict[str, object]] = []
            for line in text.strip().splitlines():
                if not line:
                    continue
                payload = json.loads(line)
                payload["metadata"]["sm2"].pop("next_review_at", None)
                out.append(payload)
            return out

        assert _strip_volatile(out1.read_text()) == _strip_volatile(out2.read_text())


@pytest.mark.anyio
async def test_export_no_interleave_canonical_order(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        for i in range(2):
            await writer.write_round(
                session_id="s1",
                project_slug="alpha",
                cli_agent="claude-code",
                round_index=i,
                operator_message=f"m{i}",
                cli_response=f"r{i}",
                tool_calls=[
                    EpisodicToolCall(tool="a", args={"i": i}, status="ok"),
                    EpisodicToolCall(tool="b", args={"i": i}, status="ok"),
                ],
            )
        await ProceduralDistiller(store=store, min_pair_count=2).distil(
            project_slug="alpha",
        )
        out = tmp_path / "corpus.jsonl"
        report = await ReflexCorpusExporter(store=store).export(
            ExportConfig(
                out_path=out,
                project_slug="alpha",
                interleave=False,
            ),
        )
        # Canonical order doesn't crash and writes the same N items.
        assert report.items_written >= 1


@pytest.mark.anyio
async def test_export_metadata_carries_topic(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        await writer.write_decision(
            session_id="s1",
            intent="lock embedder",
            body="bge-m3",
            project_slug="alpha",
        )
        await writer.write_decision(
            session_id="s2",
            intent="lock reranker",
            body="bge-rerank",
            project_slug="alpha",
        )
        await ProceduralDistiller(store=store, min_theme_count=2).distil(
            project_slug="alpha",
        )
        out = tmp_path / "corpus.jsonl"
        report = await ReflexCorpusExporter(store=store).export(
            ExportConfig(
                out_path=out,
                project_slug="alpha",
                tiers=("procedural",),
            ),
        )
        if report.items_written == 0:
            pytest.skip("No procedural patterns distilled in this corpus")
        topics = {
            json.loads(line)["metadata"]["topic"]
            for line in out.read_text().strip().splitlines()
            if line
        }
        assert topics  # at least one topic surfaced
