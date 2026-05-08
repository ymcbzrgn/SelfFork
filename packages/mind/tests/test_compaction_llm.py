"""Tests for L4 LLM-summary compactor (Order 5)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from selffork_mind.compaction import LLMSummaryCompactor, apply_plan
from selffork_mind.memory.model import Note
from selffork_mind.store import DuckDBMindStore, RetrieveConfig, StoreScope


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


async def _seed_dup_notes(store: DuckDBMindStore) -> list[Note]:
    out: list[Note] = []
    for i in range(3):
        note = Note(
            tier="episodic",
            kind="observation",
            content=f"oauth flow uses bge-m3 variant {i}",
            intent="x",
            project_slug="alpha",
            session_id="s1",
        )
        out.append(await store.upsert_note(note))
    return out


@pytest.mark.anyio
async def test_llm_summary_writes_reflection_note(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_dup_notes(store)

        async def synth(_: Sequence[Note]) -> str:
            return "Reflection: oauth → bge-m3 is the default."

        compactor = LLMSummaryCompactor(
            store=store,
            llm_summarise=synth,
            project_slug="alpha",
        )
        plan = await compactor.plan(notes=notes)
        assert plan.clusters
        # Apply: cluster reps survive, originals superseded.
        await apply_plan(plan, store=store, notes=notes)
        reflections = await store.retrieve(
            RetrieveConfig(
                tiers=("reflection",),
                scope=StoreScope(project_slug="alpha"),
            ),
        )
        assert reflections
        for h in reflections:
            payload = json.loads(h.note.content)
            assert payload["type"] == "llm_summary"
            assert "Reflection:" in payload["summary"]


@pytest.mark.anyio
async def test_llm_summary_swallows_synth_failure(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_dup_notes(store)

        async def synth(_: Sequence[Note]) -> str:
            raise RuntimeError("network down")

        compactor = LLMSummaryCompactor(
            store=store,
            llm_summarise=synth,
            project_slug="alpha",
        )
        plan = await compactor.plan(notes=notes)
        # No clusters survived → no reflections written.
        assert not plan.clusters


@pytest.mark.anyio
async def test_llm_summary_skips_empty_synth_result(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_dup_notes(store)

        async def synth(_: Sequence[Note]) -> str:
            return "    "

        compactor = LLMSummaryCompactor(
            store=store,
            llm_summarise=synth,
            project_slug="alpha",
        )
        plan = await compactor.plan(notes=notes)
        assert not plan.clusters


@pytest.mark.anyio
async def test_llm_summary_no_clusters_passthrough(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        # Single note → no cluster → no LLM call.
        note = Note(
            tier="episodic",
            kind="observation",
            content="lonely",
            intent="x",
        )
        await store.upsert_note(note)
        called = False

        async def synth(_: Sequence[Note]) -> str:
            nonlocal called
            called = True
            return "should not be called"

        compactor = LLMSummaryCompactor(store=store, llm_summarise=synth)
        plan = await compactor.plan(notes=[note])
        assert not plan.clusters
        assert called is False
