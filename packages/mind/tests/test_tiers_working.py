"""Tests for :mod:`selffork_mind.memory.tiers.working` (T1 Working block).

Real DuckDBMindStore on tmp_path — no mocks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from selffork_mind.memory.tiers import WorkingBlock, WorkingBlockManager
from selffork_mind.store import DuckDBMindStore, RetrieveConfig, StoreScope


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


def test_working_block_render_skips_empty() -> None:
    block = WorkingBlock(persona="kolaya kaçmayız", current_task="ship Order 3")
    rendered = block.render()
    assert "## persona" in rendered
    assert "## current_task" in rendered
    assert "## active_project" not in rendered
    assert "## scratchpad" not in rendered


def test_working_block_render_full() -> None:
    block = WorkingBlock(
        persona="p",
        active_project="alpha",
        current_task="task",
        scratchpad="notes",
    )
    rendered = block.render()
    assert rendered.startswith("## persona")
    assert "## scratchpad" in rendered


def test_working_block_payload_round_trip() -> None:
    block = WorkingBlock(persona="p", current_task="t")
    restored = WorkingBlock.from_payload(block.to_payload())
    assert restored.persona == "p"
    assert restored.current_task == "t"


def test_working_block_rejects_extra_fields() -> None:
    with pytest.raises(ValueError):
        WorkingBlock.model_validate({"persona": "x", "bogus": 42})


@pytest.mark.anyio
async def test_load_returns_empty_when_none(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        mgr = WorkingBlockManager(store=store)
        block = await mgr.load(project_slug="alpha", session_id="s1")
        assert block.persona == ""
        assert block.current_task == ""


@pytest.mark.anyio
async def test_save_then_load(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        mgr = WorkingBlockManager(store=store)
        await mgr.save(
            WorkingBlock(persona="p", current_task="t"),
            project_slug="alpha",
            session_id="s1",
        )
        block = await mgr.load(project_slug="alpha", session_id="s1")
        assert block.persona == "p"
        assert block.current_task == "t"


@pytest.mark.anyio
async def test_save_supersedes_prior_block(tmp_path: Path) -> None:
    """Two saves → only the most recent is currently valid."""
    async with open_store(tmp_path / "x.duckdb") as store:
        mgr = WorkingBlockManager(store=store)
        await mgr.save(
            WorkingBlock(persona="first"),
            project_slug="alpha",
            session_id="s1",
        )
        await mgr.save(
            WorkingBlock(persona="second"),
            project_slug="alpha",
            session_id="s1",
        )
        # Currently-valid retrieval surfaces only one row.
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("working",),
                scope=StoreScope(project_slug="alpha", session_id="s1"),
            ),
        )
        assert len(hits) == 1
        block = await mgr.load(project_slug="alpha", session_id="s1")
        assert block.persona == "second"


@pytest.mark.anyio
async def test_clear_supersedes_all(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        mgr = WorkingBlockManager(store=store)
        await mgr.save(
            WorkingBlock(persona="x"),
            project_slug="alpha",
            session_id="s1",
        )
        await mgr.clear(project_slug="alpha", session_id="s1")
        block = await mgr.load(project_slug="alpha", session_id="s1")
        assert block.persona == ""


@pytest.mark.anyio
async def test_patch_modifies_only_named_fields(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        mgr = WorkingBlockManager(store=store)
        await mgr.save(
            WorkingBlock(persona="p", current_task="old"),
            project_slug="alpha",
            session_id="s1",
        )
        patched = await mgr.patch(
            project_slug="alpha",
            session_id="s1",
            current_task="new",
        )
        assert patched.persona == "p"
        assert patched.current_task == "new"


@pytest.mark.anyio
async def test_patch_no_changes_returns_existing(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        mgr = WorkingBlockManager(store=store)
        await mgr.save(
            WorkingBlock(persona="p"),
            project_slug="alpha",
            session_id="s1",
        )
        result = await mgr.patch(project_slug="alpha", session_id="s1")
        assert result.persona == "p"


@pytest.mark.anyio
async def test_multi_project_isolation(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        mgr = WorkingBlockManager(store=store)
        await mgr.save(
            WorkingBlock(persona="alpha"),
            project_slug="alpha",
            session_id="s1",
        )
        await mgr.save(
            WorkingBlock(persona="beta"),
            project_slug="beta",
            session_id="s1",
        )
        a = await mgr.load(project_slug="alpha", session_id="s1")
        b = await mgr.load(project_slug="beta", session_id="s1")
        assert a.persona == "alpha"
        assert b.persona == "beta"


@pytest.mark.anyio
async def test_orphan_session_supported(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        mgr = WorkingBlockManager(store=store)
        await mgr.save(
            WorkingBlock(persona="orphan"),
            project_slug=None,
            session_id="s1",
        )
        block = await mgr.load(project_slug=None, session_id="s1")
        assert block.persona == "orphan"


@pytest.mark.anyio
async def test_block_pinned_and_high_importance(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        mgr = WorkingBlockManager(store=store)
        await mgr.save(
            WorkingBlock(persona="p"),
            project_slug="alpha",
            session_id="s1",
        )
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("working",),
                scope=StoreScope(project_slug="alpha", session_id="s1"),
            ),
        )
        assert hits[0].note.pinned is True
        assert hits[0].note.importance >= 10.0


@pytest.mark.anyio
async def test_load_tolerates_corrupt_payload(tmp_path: Path) -> None:
    """Garbage stored content → manager returns an empty block, not a crash."""
    from selffork_mind.memory.model import Note

    async with open_store(tmp_path / "x.duckdb") as store:
        await store.upsert_note(
            Note(
                tier="working",
                kind="pointer",
                content="this is not json {{{",
                intent="working_block",
                project_slug="alpha",
                session_id="s1",
            ),
        )
        mgr = WorkingBlockManager(store=store)
        block = await mgr.load(project_slug="alpha", session_id="s1")
        assert block.persona == ""
