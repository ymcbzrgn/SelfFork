"""Tests for :mod:`selffork_mind.memory.tiers.procedural`."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from selffork_mind.memory.tiers import (
    EpisodicToolCall,
    EpisodicWriter,
    ProceduralDistiller,
)
from selffork_mind.memory.tiers.procedural import _intent_tokens
from selffork_mind.store import DuckDBMindStore, RetrieveConfig, StoreScope


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


def test_intent_tokens_strips_stopwords() -> None:
    assert _intent_tokens("the lock of embedder") == ["lock", "embedder"]


def test_intent_tokens_handles_unicode() -> None:
    assert _intent_tokens("naber dünyâ") == ["naber", "dünyâ"]


def test_intent_tokens_strips_punctuation() -> None:
    assert _intent_tokens("plan: ship-it") == ["plan", "shipit"]


@pytest.mark.anyio
async def test_distil_no_episodic_returns_empty(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        distiller = ProceduralDistiller(store=store)
        report = await distiller.distil(project_slug="alpha")
        assert report.candidates_examined == 0
        assert report.patterns_written == 0


@pytest.mark.anyio
async def test_tool_sequence_detected(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        # Two rounds, each with the same A→B tool sequence (distinct args
        # so UUID5 dedup doesn't collapse the pattern notes).
        for round_index in range(2):
            await writer.write_round(
                session_id="s1",
                project_slug="alpha",
                cli_agent="claude-code",
                round_index=round_index,
                operator_message=f"round {round_index}",
                cli_response="ok",
                tool_calls=[
                    EpisodicToolCall(
                        tool="kanban_card_done",
                        args={"round": round_index},
                        status="ok",
                    ),
                    EpisodicToolCall(
                        tool="mind_note_add",
                        args={"round": round_index},
                        status="ok",
                    ),
                ],
            )
        distiller = ProceduralDistiller(store=store, min_pair_count=2)
        report = await distiller.distil(project_slug="alpha")
        assert report.tool_sequences >= 1
        assert report.patterns_written >= 1
        # Procedural notes exist in the store now.
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("procedural",),
                scope=StoreScope(project_slug="alpha"),
            ),
        )
        contents = [json.loads(h.note.content) for h in hits]
        types = {c.get("type") for c in contents}
        assert "tool_sequence" in types


@pytest.mark.anyio
async def test_decision_theme_detected(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        await writer.write_decision(
            session_id="s1",
            intent="lock embedder bge",
            body="bge-m3",
            project_slug="alpha",
        )
        await writer.write_decision(
            session_id="s2",
            intent="lock embedder jina",
            body="jina v3",
            project_slug="alpha",
        )
        distiller = ProceduralDistiller(store=store, min_theme_count=2)
        report = await distiller.distil(project_slug="alpha")
        assert report.decision_themes >= 1
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("procedural",),
                scope=StoreScope(project_slug="alpha"),
            ),
        )
        types = {json.loads(h.note.content).get("type") for h in hits}
        assert "decision_theme" in types


@pytest.mark.anyio
async def test_sentinel_routine_detected(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        for round_index in range(2):
            # Distinct operator messages so UUID5 dedup keeps both notes.
            await writer.write_round(
                session_id="s1",
                project_slug="alpha",
                cli_agent="claude-code",
                round_index=round_index,
                operator_message=f"finish step {round_index} [SELFFORK:DONE]",
                cli_response=f"ack {round_index}",
            )
        distiller = ProceduralDistiller(store=store, min_theme_count=2)
        report = await distiller.distil(project_slug="alpha")
        assert report.sentinel_routines >= 1


@pytest.mark.anyio
async def test_distil_idempotent(tmp_path: Path) -> None:
    """Running distil twice over the same corpus does not duplicate patterns."""
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
                    EpisodicToolCall(tool="a", args={"r": i}, status="ok"),
                    EpisodicToolCall(tool="b", args={"r": i}, status="ok"),
                ],
            )
        distiller = ProceduralDistiller(store=store, min_pair_count=2)
        first = await distiller.distil(project_slug="alpha")
        second = await distiller.distil(project_slug="alpha")
        # Stored Procedural count after second pass is still equal to first's
        # output (UUID5 dedup).
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("procedural",),
                scope=StoreScope(project_slug="alpha"),
            ),
        )
        assert len(hits) == first.patterns_written
        assert second.patterns_written == first.patterns_written


@pytest.mark.anyio
async def test_distil_below_threshold_skipped(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        # Single-round single-pair → below default min_pair_count=2.
        await writer.write_round(
            session_id="s1",
            project_slug="alpha",
            cli_agent="claude-code",
            round_index=0,
            operator_message="m",
            cli_response="r",
            tool_calls=[
                EpisodicToolCall(tool="a", args={}, status="ok"),
                EpisodicToolCall(tool="b", args={}, status="ok"),
            ],
        )
        distiller = ProceduralDistiller(store=store, min_pair_count=2)
        report = await distiller.distil(project_slug="alpha")
        assert report.tool_sequences == 0


@pytest.mark.anyio
async def test_distil_scoped_by_session(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        for sid in ("sa", "sb"):
            await writer.write_round(
                session_id=sid,
                project_slug="alpha",
                cli_agent="claude-code",
                round_index=0,
                operator_message="m",
                cli_response="r",
            )
        distiller = ProceduralDistiller(store=store, min_theme_count=1)
        # session_id="sa" must not pull in sb's notes
        report = await distiller.distil(project_slug="alpha", session_id="sa")
        # No tool calls, no decisions; observations carry no sentinel — zero
        # patterns expected. The candidates_examined count proves the scope
        # filter worked.
        assert report.candidates_examined == 1


@pytest.mark.anyio
async def test_pattern_notes_carry_kind_tag(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        for round_index in range(2):
            await writer.write_round(
                session_id="s1",
                project_slug="alpha",
                cli_agent="claude-code",
                round_index=round_index,
                operator_message=f"m{round_index}",
                cli_response=f"r{round_index}",
                tool_calls=[
                    EpisodicToolCall(tool="a", args={"r": round_index}, status="ok"),
                    EpisodicToolCall(tool="b", args={"r": round_index}, status="ok"),
                ],
            )
        distiller = ProceduralDistiller(store=store, min_pair_count=2)
        await distiller.distil(project_slug="alpha")
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("procedural",),
                scope=StoreScope(project_slug="alpha"),
            ),
        )
        for h in hits:
            tags = await store.list_tags(h.note.id)
            keys = {t.key for t in tags}
            assert "kind" in keys
            assert "project" in keys
            assert "distilled_from" in keys


@pytest.mark.anyio
async def test_orphan_distil_works(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        for round_index in range(2):
            await writer.write_round(
                session_id="s1",
                project_slug=None,
                cli_agent="claude-code",
                round_index=round_index,
                operator_message=f"m{round_index}",
                cli_response=f"r{round_index}",
                tool_calls=[
                    EpisodicToolCall(tool="a", args={"r": round_index}, status="ok"),
                    EpisodicToolCall(tool="b", args={"r": round_index}, status="ok"),
                ],
            )
        distiller = ProceduralDistiller(store=store, min_pair_count=2)
        report = await distiller.distil(project_slug=None)
        assert report.tool_sequences >= 1


@pytest.mark.anyio
async def test_extract_tool_name_falls_back_to_intent(tmp_path: Path) -> None:
    """If the pattern note's content isn't valid JSON, distiller still
    finds the tool name via the ``tool:foo`` intent prefix.
    """
    async with open_store(tmp_path / "x.duckdb") as store:
        from selffork_mind.memory.model import Note

        for i in range(2):
            for tool in ("a", "b"):
                await store.upsert_note(
                    Note(
                        tier="episodic",
                        kind="pattern",
                        content=f"not-json-{i}-{tool}",  # distinct → no dedup
                        intent=f"tool:{tool}",
                        project_slug="alpha",
                        session_id="s1",
                        source_pointer=f"audit:s1:round:{i}:tool:{tool}",
                    ),
                )
        distiller = ProceduralDistiller(store=store, min_pair_count=2)
        report = await distiller.distil(project_slug="alpha")
        assert report.tool_sequences >= 1
