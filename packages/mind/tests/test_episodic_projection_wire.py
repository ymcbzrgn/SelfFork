"""Tests for the EpisodicWriter ↔ MarkdownProjection wiring (Order 2.6)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from selffork_mind.memory.tiers import EpisodicWriter
from selffork_mind.projections.markdown import (
    MarkdownProjection,
    MarkdownProjectionConfig,
)
from selffork_mind.store import DuckDBMindStore, StoreScope


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


@pytest.mark.anyio
async def test_write_round_refreshes_projection(tmp_path: Path) -> None:
    md_root = tmp_path / "markdown"
    projection = MarkdownProjection(MarkdownProjectionConfig(root=md_root))
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(
            store=store,
            projection=projection,
            projection_scope=StoreScope(project_slug="alpha"),
        )
        await writer.write_round(
            session_id="s1",
            project_slug="alpha",
            cli_agent="claude-code",
            round_index=0,
            operator_message="m",
            cli_response="r",
        )
        index_path = md_root / "MEMORY.md"
        assert index_path.is_file()
        body = index_path.read_text(encoding="utf-8")
        assert "MEMORY.md" in body


@pytest.mark.anyio
async def test_write_decision_refreshes_projection(tmp_path: Path) -> None:
    md_root = tmp_path / "markdown"
    projection = MarkdownProjection(MarkdownProjectionConfig(root=md_root))
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(
            store=store,
            projection=projection,
            projection_scope=StoreScope(project_slug="alpha"),
        )
        note = await writer.write_decision(
            session_id="s1",
            intent="lock",
            body="lock body",
            project_slug="alpha",
        )
        topic_path = md_root / "topics" / f"{note.id}.md"
        assert topic_path.is_file()
        body = topic_path.read_text(encoding="utf-8")
        assert "lock body" in body


@pytest.mark.anyio
async def test_no_projection_when_none_wired(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        await writer.write_round(
            session_id="s1",
            project_slug="alpha",
            cli_agent="claude-code",
            round_index=0,
            operator_message="m",
            cli_response="r",
        )
        # No markdown root was provided, so nothing should be on disk.
        assert not (tmp_path / "MEMORY.md").exists()


@pytest.mark.anyio
async def test_projection_swallows_oserror(tmp_path: Path) -> None:
    """Pass an unwritable root; ensure the writer still completes."""
    md_root = tmp_path / "no" / "such" / "writable" / "place"
    # Make a file at the parent so mkdir fails cleanly.
    (tmp_path / "no").touch()
    projection = MarkdownProjection(MarkdownProjectionConfig(root=md_root))
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store, projection=projection)
        notes = await writer.write_round(
            session_id="s1",
            project_slug=None,
            cli_agent="claude-code",
            round_index=0,
            operator_message="m",
            cli_response="r",
        )
        assert notes  # write_round still succeeded
