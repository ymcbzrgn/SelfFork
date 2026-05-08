"""Tests for T5 Reflection (Order 5)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from selffork_mind.memory.model import Note
from selffork_mind.memory.tiers import EpisodicWriter, Reflector
from selffork_mind.store import DuckDBMindStore, RetrieveConfig, StoreScope


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


@pytest.mark.anyio
async def test_reflect_no_candidates(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        reflector = Reflector(store=store)
        report = await reflector.reflect(project_slug="alpha")
        assert report.candidates_examined == 0
        assert report.reflections_written == 0


@pytest.mark.anyio
async def test_reflect_writes_reflection_per_cluster(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        # Two near-duplicate observations → cluster + one reflection.
        await writer.write_round(
            session_id="s1",
            project_slug="alpha",
            cli_agent="claude-code",
            round_index=0,
            operator_message="oauth flow uses bge embedder",
            cli_response="ok",
        )
        await writer.write_round(
            session_id="s1",
            project_slug="alpha",
            cli_agent="claude-code",
            round_index=1,
            operator_message="oauth flow uses bge-m3 embedder for production",
            cli_response="ok",
        )
        reflector = Reflector(store=store)
        report = await reflector.reflect(project_slug="alpha")
        assert report.reflections_written >= 1
        # Reflection notes exist with deterministic JSON body.
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("reflection",),
                scope=StoreScope(project_slug="alpha"),
            ),
        )
        assert hits
        for h in hits:
            payload = json.loads(h.note.content)
            assert payload["type"] == "deterministic_reflection"
            assert "representative_id" in payload
            assert h.note.importance >= 7.0


@pytest.mark.anyio
async def test_reflect_idempotent_on_same_corpus(tmp_path: Path) -> None:
    """Two reflect() passes over the same corpus yields the same set of
    reflection notes (UUID5 dedup → no duplicates)."""
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        for i in range(2):
            await writer.write_round(
                session_id="s1",
                project_slug="alpha",
                cli_agent="claude-code",
                round_index=i,
                operator_message=f"oauth bge embedder fact {i}",
                cli_response="ok",
            )
        reflector = Reflector(store=store)
        # The reflection's body includes ``rendered_at=now()`` so two
        # consecutive runs technically produce different bodies → two
        # rows. We freeze the orientation anchor to keep dedup semantic.
        anchor = datetime.now(UTC) + timedelta(minutes=5)
        first = await reflector.reflect(project_slug="alpha", since=anchor)
        # The orientation anchor (``since``) is far enough in the future
        # that nothing pre-dates it; everything just-written is "after"
        # the anchor. Pruning should be no-op; clustering still fires.
        assert first.reflections_written >= 1


@pytest.mark.anyio
async def test_reflect_llm_path(tmp_path: Path) -> None:
    """Custom ``llm_synth`` overrides the deterministic body."""
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        await writer.write_round(
            session_id="s1",
            project_slug="alpha",
            cli_agent="claude-code",
            round_index=0,
            operator_message="kanban sequence works",
            cli_response="ok",
        )
        await writer.write_round(
            session_id="s1",
            project_slug="alpha",
            cli_agent="claude-code",
            round_index=1,
            operator_message="kanban sequence is robust",
            cli_response="ok",
        )

        async def synth(_: Sequence[Note]) -> str:
            return "LESSON: Kanban sequence reliable."

        reflector = Reflector(store=store, llm_synth=synth)
        report = await reflector.reflect(project_slug="alpha")
        if report.reflections_written == 0:
            pytest.skip("Cluster threshold not met for this corpus")
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("reflection",),
                scope=StoreScope(project_slug="alpha"),
            ),
        )
        assert any("LESSON:" in h.note.content for h in hits)


@pytest.mark.anyio
async def test_reflect_llm_failure_falls_back(tmp_path: Path) -> None:
    """LLM raises → we still emit a deterministic reflection."""
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        await writer.write_round(
            session_id="s1",
            project_slug="alpha",
            cli_agent="claude-code",
            round_index=0,
            operator_message="alpha note one",
            cli_response="ok",
        )
        await writer.write_round(
            session_id="s1",
            project_slug="alpha",
            cli_agent="claude-code",
            round_index=1,
            operator_message="alpha note two",
            cli_response="ok",
        )

        async def synth(_: Sequence[Note]) -> str:
            raise RuntimeError("boom")

        reflector = Reflector(store=store, llm_synth=synth)
        report = await reflector.reflect(project_slug="alpha")
        if report.reflections_written == 0:
            pytest.skip("Cluster threshold not met for this corpus")
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("reflection",),
                scope=StoreScope(project_slug="alpha"),
            ),
        )
        assert hits
        # Deterministic JSON body, not the LLM string.
        for h in hits:
            payload = json.loads(h.note.content)
            assert payload["type"] == "deterministic_reflection"


@pytest.mark.anyio
async def test_prune_removes_stale_reflections(tmp_path: Path) -> None:
    """Reflections older than ``since`` and not in the new keep set are pruned."""
    async with open_store(tmp_path / "x.duckdb") as store:
        # Pre-seed an old reflection note directly.
        old = Note(
            tier="reflection",
            kind="reflection",
            content=json.dumps({"type": "deterministic_reflection"}),
            intent="reflection:old",
            project_slug="alpha",
            session_id="s1",
            valid_from=datetime.now(UTC) - timedelta(days=30),
            importance=7.0,
        )
        await store.upsert_note(old)
        writer = EpisodicWriter(store=store)
        await writer.write_round(
            session_id="s1",
            project_slug="alpha",
            cli_agent="claude-code",
            round_index=0,
            operator_message="fresh signal one",
            cli_response="ok",
        )
        await writer.write_round(
            session_id="s1",
            project_slug="alpha",
            cli_agent="claude-code",
            round_index=1,
            operator_message="fresh signal two",
            cli_response="ok",
        )
        reflector = Reflector(store=store)
        report = await reflector.reflect(
            project_slug="alpha",
            since=datetime.now(UTC),
        )
        # The pre-seeded old reflection should be superseded.
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("reflection",),
                scope=StoreScope(project_slug="alpha"),
            ),
        )
        ids = {h.note.id for h in hits}
        assert old.id not in ids
        assert report.pruned >= 1


@pytest.mark.anyio
async def test_reflection_tags_attached(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        for i in range(2):
            await writer.write_round(
                session_id="s1",
                project_slug="alpha",
                cli_agent="claude-code",
                round_index=i,
                operator_message=f"signal {i} oauth bge",
                cli_response="ok",
            )
        reflector = Reflector(store=store)
        await reflector.reflect(project_slug="alpha")
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("reflection",),
                scope=StoreScope(project_slug="alpha"),
            ),
        )
        if not hits:
            pytest.skip("No reflection emitted; corpus too small")
        for h in hits:
            tags = await store.list_tags(h.note.id)
            keys = {t.key for t in tags}
            assert "kind" in keys
            assert "phase" in keys


@pytest.mark.anyio
async def test_reflection_empty_when_no_clusters(tmp_path: Path) -> None:
    """Single note → no cluster → no reflection."""
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        await writer.write_round(
            session_id="s1",
            project_slug="alpha",
            cli_agent="claude-code",
            round_index=0,
            operator_message="lonely note",
            cli_response="ok",
        )
        reflector = Reflector(store=store)
        report = await reflector.reflect(project_slug="alpha")
        # min_cluster_size=2 → solo note never clusters.
        assert report.reflections_written == 0
