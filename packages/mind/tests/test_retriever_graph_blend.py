"""HybridRetriever ↔ GraphRetriever blending (Order 4 §5)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from selffork_mind.graph import (
    GraphRetriever,
    InMemoryGraphStore,
    SemanticGraphConsolidator,
)
from selffork_mind.memory.tiers import EpisodicWriter
from selffork_mind.rag.retriever import HybridRetriever, classify_query
from selffork_mind.store import DuckDBMindStore


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


@pytest.mark.anyio
async def test_temporal_query_blends_graph_with_vector(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as mind:
        graph = InMemoryGraphStore()
        writer = EpisodicWriter(store=mind)
        await writer.write_decision(
            session_id="s1",
            intent="oauth note",
            body="oauth flow uses bge",
            project_slug="alpha",
        )
        await writer.write_decision(
            session_id="s1",
            intent="kanban note",
            body="kanban path is at packages",
            project_slug="alpha",
        )
        consol = SemanticGraphConsolidator(store=mind, graph=graph)
        await consol.consolidate(project_slug="alpha")
        graph_retriever = GraphRetriever(store=mind, graph=graph)

        retriever = HybridRetriever(
            store=mind,
            embedder=None,
            graph_retriever=graph_retriever,
        )
        # "when did we lock the embedder" classifies as hybrid → graph fires.
        hits = await retriever.recall(
            query="when did we lock the embedder",
            top_k=5,
        )
        # The graph route must contribute SOMETHING relevant. With BM25 alone
        # the seed phrases ("when", "did", …) wouldn't reach our corpus, but
        # graph PPR can still surface a passage when "embedder" matches a
        # phrase in the bge note.
        assert hits  # not empty


@pytest.mark.anyio
async def test_vector_query_skips_graph(tmp_path: Path) -> None:
    """Single-fact queries classify as vector → graph not consulted."""
    async with open_store(tmp_path / "x.duckdb") as mind:
        graph = InMemoryGraphStore()
        retriever = HybridRetriever(
            store=mind,
            embedder=None,
            graph_retriever=GraphRetriever(store=mind, graph=graph),
        )
        # No notes, no graph; just verify the vector route doesn't crash.
        hits = await retriever.recall(query="oauth flow embedder", top_k=5)
        assert classify_query("oauth flow embedder") == "vector"
        assert hits == []


@pytest.mark.anyio
async def test_graph_route_active_with_empty_vector_store(tmp_path: Path) -> None:
    """Regression: when vector store is empty AND query classifies hybrid,
    graph PPR must still be consulted (Order 4 audit Finding #6)."""
    from selffork_mind.memory.tiers import EpisodicWriter

    async with open_store(tmp_path / "x.duckdb") as mind:
        graph = InMemoryGraphStore()
        # Seed the graph WITHOUT any matching vector candidates by giving
        # the EpisodicWriter writes a totally orthogonal session_id; we
        # consolidate, then clear-by-scope at retrieval time so the
        # Mind scope filter excludes them from the vector path while the
        # graph index still holds the phrases.
        writer = EpisodicWriter(store=mind)
        await writer.write_decision(
            session_id="graph-only",
            intent="oauth",
            body="oauth flow uses bge-m3 embedder",
            project_slug="graph-source",
        )
        consol = SemanticGraphConsolidator(store=mind, graph=graph)
        await consol.consolidate(project_slug="graph-source")

        graph_retriever = GraphRetriever(store=mind, graph=graph)
        retriever = HybridRetriever(
            store=mind,
            embedder=None,
            graph_retriever=graph_retriever,
        )
        # Hybrid query against a DIFFERENT project_slug → vector candidates
        # zero (StoreScope filters out the seeded notes). Graph should
        # still surface the bge passage via the shared phrase.
        from selffork_mind.store import StoreScope

        hits = await retriever.recall(
            query="when did we lock the embedder",
            scope=StoreScope(project_slug="cold-project"),
            top_k=5,
        )
        # Note: graph_retriever returns notes by id without scope filtering,
        # so the cold-project query can reach the graph-source passage.
        # The blended score may be > 0 → at least one hit surfaces.
        assert len(hits) >= 1


@pytest.mark.anyio
async def test_provenance_records_graph_tag(tmp_path: Path) -> None:
    from selffork_mind.projections.provenance import ProvenanceRecorder

    async with open_store(tmp_path / "x.duckdb") as mind:
        graph = InMemoryGraphStore()
        log_path = tmp_path / "provenance.jsonl"
        recorder = ProvenanceRecorder(log_path=log_path)
        retriever = HybridRetriever(
            store=mind,
            embedder=None,
            provenance=recorder,
            graph_retriever=GraphRetriever(store=mind, graph=graph),
        )
        await retriever.recall(
            query="when was the embedder locked",
            session_id="s",
        )
        entries = recorder.read_all()
        assert entries
        assert "+graph" in entries[0].retriever
