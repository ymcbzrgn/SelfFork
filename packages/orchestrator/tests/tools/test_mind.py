"""Tests for ``mind_recall`` + ``mind_note_add`` tools.

Real DuckDB store + retriever — no mocks. Tools are sync handlers; the
async Mind APIs are bridged via ``asyncio.run`` inside the handler. We
test that registry registration, parser round-trip, happy paths, error
paths (Mind disabled / invalid args / unknown tier-kind) all behave.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from selffork_mind.memory.tiers import EpisodicWriter
from selffork_mind.rag.retriever import HybridRetriever
from selffork_mind.store import DuckDBMindStore, RetrieveConfig, StoreScope
from selffork_orchestrator.tools import (
    ToolCall,
    ToolContext,
    build_default_registry,
)
from selffork_orchestrator.tools.mind import build_mind_tools
from selffork_orchestrator.tools.parser import parse_tool_calls


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


# ── registry ──────────────────────────────────────────────────────────────


def test_default_registry_includes_mind_tools() -> None:
    reg = build_default_registry()
    names = reg.names()
    assert "mind_recall" in names
    assert "mind_note_add" in names


def test_build_mind_tools_returns_two_specs() -> None:
    specs = build_mind_tools()
    assert {s.name for s in specs} == {"mind_recall", "mind_note_add"}


# ── parser round-trip ─────────────────────────────────────────────────────


def test_parser_round_trip_mind_recall_block() -> None:
    block = (
        "<selffork-tool-call>\n"
        '{"tool": "mind_recall", "args": {"query": "x", "top_k": 3}}\n'
        "</selffork-tool-call>"
    )
    calls = parse_tool_calls(block)
    assert len(calls) == 1
    assert calls[0].tool == "mind_recall"
    assert calls[0].args == {"query": "x", "top_k": 3}


def test_parser_round_trip_mind_note_add_block() -> None:
    block = (
        "<selffork-tool-call>\n"
        '{"tool": "mind_note_add", "args": '
        '{"content": "x", "tier": "episodic", "kind": "decision"}}\n'
        "</selffork-tool-call>"
    )
    calls = parse_tool_calls(block)
    assert calls[0].tool == "mind_note_add"
    assert calls[0].args["kind"] == "decision"


# ── mind_recall ───────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_mind_recall_unauthorized_when_retriever_none(tmp_path: Path) -> None:
    """When retriever is None (Mind disabled), result is unauthorized."""
    del tmp_path
    reg = build_default_registry()
    ctx = ToolContext(
        session_id="s",
        project_slug="p",
        project_store=object(),
        mind_retriever=None,
    )
    call = ToolCall(tool="mind_recall", args={"query": "x"}, order_in_reply=0)
    result = await reg.invoke_async(call, ctx)
    assert result.status == "unauthorized"
    assert "mind_retriever is None" in (result.error or "")


@pytest.mark.anyio
async def test_mind_recall_returns_hits(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        await writer.write_decision(
            session_id="s1",
            intent="lock",
            body="OAuth flow uses bge-m3 embedder",
            project_slug="p1",
        )
        retriever = HybridRetriever(store=store, embedder=None)
        reg = build_default_registry()
        ctx = ToolContext(
            session_id="s1",
            project_slug="p1",
            project_store=object(),
            mind_retriever=retriever,
        )
        call = ToolCall(
            tool="mind_recall",
            args={"query": "oauth bge", "top_k": 5},
            order_in_reply=0,
        )
        # Synchronous registry call — but we're already in an async test.
        result = await reg.invoke_async(call, ctx)
        assert result.status == "ok"
        payload = result.payload or {}
        assert payload["query"] == "oauth bge"
        assert payload["hit_count"] >= 1
        assert any("bge-m3" in h["content"] for h in payload["hits"])


@pytest.mark.anyio
async def test_mind_recall_unknown_tier_returns_error_payload(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        retriever = HybridRetriever(store=store)
        reg = build_default_registry()
        ctx = ToolContext(
            session_id="s",
            project_slug=None,
            project_store=object(),
            mind_retriever=retriever,
        )
        call = ToolCall(
            tool="mind_recall",
            args={"query": "x", "tier": "totally-bogus"},
            order_in_reply=0,
        )
        result = await reg.invoke_async(call, ctx)
        assert result.status == "ok"
        payload = result.payload or {}
        assert "error" in payload
        assert payload["hits"] == []


@pytest.mark.anyio
async def test_mind_recall_invalid_args(tmp_path: Path) -> None:
    """Pydantic validation: empty query rejected."""
    async with open_store(tmp_path / "x.duckdb") as store:
        retriever = HybridRetriever(store=store)
        reg = build_default_registry()
        ctx = ToolContext(
            session_id="s",
            project_slug=None,
            project_store=object(),
            mind_retriever=retriever,
        )
        call = ToolCall(
            tool="mind_recall",
            args={"query": ""},
            order_in_reply=0,
        )
        result = await reg.invoke_async(call, ctx)
        assert result.status == "invalid_args"


@pytest.mark.anyio
async def test_mind_recall_scope_filters_by_project(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        await writer.write_decision(
            session_id="sa",
            intent="alpha",
            body="alpha note",
            project_slug="alpha",
        )
        await writer.write_decision(
            session_id="sb",
            intent="beta",
            body="alpha note",  # same body
            project_slug="beta",
        )
        retriever = HybridRetriever(store=store)
        reg = build_default_registry()
        ctx = ToolContext(
            session_id="x",
            project_slug="alpha",
            project_store=object(),
            mind_retriever=retriever,
        )
        call = ToolCall(
            tool="mind_recall",
            args={"query": "alpha"},
            order_in_reply=0,
        )
        result = await reg.invoke_async(call, ctx)
        payload = result.payload or {}
        # Only alpha results returned.
        assert all(h["project_slug"] == "alpha" for h in payload["hits"])


# ── mind_note_add ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_mind_note_add_unauthorized_when_writer_none(tmp_path: Path) -> None:
    del tmp_path
    reg = build_default_registry()
    ctx = ToolContext(
        session_id="s",
        project_slug="p",
        project_store=object(),
        mind_store=None,
        episodic_writer=None,
    )
    call = ToolCall(
        tool="mind_note_add",
        args={"content": "x"},
        order_in_reply=0,
    )
    result = await reg.invoke_async(call, ctx)
    assert result.status == "unauthorized"


@pytest.mark.anyio
async def test_mind_note_add_writes_observation(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        reg = build_default_registry()
        ctx = ToolContext(
            session_id="s1",
            project_slug="p1",
            project_store=object(),
            mind_store=store,
            episodic_writer=writer,
            cli_agent_name="claude-code",
        )
        call = ToolCall(
            tool="mind_note_add",
            args={
                "content": "captured insight",
                "kind": "observation",
                "intent": "captured",
            },
            order_in_reply=0,
        )
        result = await reg.invoke_async(call, ctx)
        assert result.status == "ok"
        payload = result.payload or {}
        ids = payload["ids"]
        assert ids
        # Note actually persisted
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("episodic",),
                scope=StoreScope(project_slug="p1"),
            ),
        )
        assert any("captured insight" in h.note.content for h in hits)


@pytest.mark.anyio
async def test_mind_note_add_writes_decision_with_higher_importance(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        reg = build_default_registry()
        ctx = ToolContext(
            session_id="s1",
            project_slug="p1",
            project_store=object(),
            mind_store=store,
            episodic_writer=writer,
            cli_agent_name="claude-code",
        )
        call = ToolCall(
            tool="mind_note_add",
            args={
                "content": "lock embedder",
                "kind": "decision",
                "intent": "lock",
            },
            order_in_reply=0,
        )
        result = await reg.invoke_async(call, ctx)
        assert result.status == "ok"
        payload = result.payload or {}
        from uuid import UUID

        note = await store.get_note(UUID(payload["ids"][0]))
        assert note is not None
        assert note.kind == "decision"
        assert note.importance >= 5.0


@pytest.mark.anyio
async def test_mind_note_add_attaches_tag_pairs(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        reg = build_default_registry()
        ctx = ToolContext(
            session_id="s1",
            project_slug="p1",
            project_store=object(),
            mind_store=store,
            episodic_writer=writer,
            cli_agent_name="claude-code",
        )
        call = ToolCall(
            tool="mind_note_add",
            args={
                "content": "tagged note",
                "kind": "observation",
                "tag_pairs": [["topic", "embedder"], ["mood", "decisive"]],
            },
            order_in_reply=0,
        )
        result = await reg.invoke_async(call, ctx)
        assert result.status == "ok"
        from uuid import UUID

        nid = UUID((result.payload or {})["ids"][0])
        tags = await store.list_tags(nid)
        as_pairs = {(t.key, t.value) for t in tags}
        assert ("topic", "embedder") in as_pairs
        assert ("mood", "decisive") in as_pairs


@pytest.mark.anyio
async def test_mind_note_add_invalid_tier(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        reg = build_default_registry()
        ctx = ToolContext(
            session_id="s1",
            project_slug="p1",
            project_store=object(),
            mind_store=store,
            episodic_writer=writer,
        )
        call = ToolCall(
            tool="mind_note_add",
            args={"content": "x", "tier": "totally-bogus"},
            order_in_reply=0,
        )
        result = await reg.invoke_async(call, ctx)
        # Pydantic doesn't reject (no Literal); handler returns error payload.
        assert result.status == "ok"
        assert "error" in (result.payload or {})


@pytest.mark.anyio
async def test_mind_note_add_invalid_tag_pair_shape(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        reg = build_default_registry()
        ctx = ToolContext(
            session_id="s1",
            project_slug="p1",
            project_store=object(),
            mind_store=store,
            episodic_writer=writer,
        )
        call = ToolCall(
            tool="mind_note_add",
            args={
                "content": "x",
                "tag_pairs": [["only-one"]],  # wrong shape
            },
            order_in_reply=0,
        )
        result = await reg.invoke_async(call, ctx)
        assert "error" in (result.payload or {})
