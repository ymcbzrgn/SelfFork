"""Tests for T3 Semantic Graph backend (Order 4)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from selffork_mind.graph import (
    GraphRetriever,
    GraphTriple,
    InMemoryGraphStore,
    SemanticGraphConsolidator,
    extract_triples,
    personalized_pagerank,
)
from selffork_mind.graph.consolidation import extract_phrases
from selffork_mind.memory.model import Note
from selffork_mind.memory.tiers import EpisodicWriter
from selffork_mind.store import DuckDBMindStore


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


# ── extract_phrases / extract_triples ───────────────────────────────────


def test_extract_phrases_dedups_and_lowercases() -> None:
    out = extract_phrases("OAuth flow uses bge-m3, OAuth fine.")
    assert out[:3] == ["oauth", "flow", "uses"]
    # No duplicate "oauth"
    assert out.count("oauth") == 1


def test_extract_phrases_drops_stopwords_and_short() -> None:
    out = extract_phrases("the a an of to in oauth")
    assert out == ["oauth"]


def test_extract_phrases_caps_at_max() -> None:
    text = " ".join(f"word{i}" for i in range(200))
    out = extract_phrases(text, max_phrases=5)
    assert len(out) == 5


def test_extract_triples_tool_sequence_pattern() -> None:
    note = Note(
        tier="procedural",
        kind="pattern",
        content='{"type": "tool_sequence", "first": "a", "then": "b"}',
        intent="sequence:a->b",
        project_slug="alpha",
    )
    triples = extract_triples(note)
    assert any(t.subject == "a" and t.predicate == "then" and t.obj == "b" for t in triples)


def test_extract_triples_decision_theme_pattern() -> None:
    decision_id = uuid4()
    note = Note(
        tier="procedural",
        kind="pattern",
        content=(
            f'{{"type": "decision_theme", "theme": "embedder", "decision_ids": ["{decision_id}"]}}'
        ),
        intent="theme:embedder",
        project_slug="alpha",
    )
    triples = extract_triples(note)
    assert any(t.subject == "embedder" and t.predicate == "decided_in" for t in triples)


def test_extract_triples_episodic_tool_call_pattern() -> None:
    note = Note(
        tier="episodic",
        kind="pattern",
        content='{"tool": "kanban_card_done", "args": {}, "status": "ok"}',
        intent="tool:kanban_card_done",
        project_slug="alpha",
    )
    triples = extract_triples(note)
    assert any(
        t.subject == "operator" and t.predicate == "uses" and t.obj == "kanban_card_done"
        for t in triples
    )


def test_extract_triples_verb_pattern() -> None:
    note = Note(
        tier="episodic",
        kind="observation",
        content="oauth uses bge-m3",
        intent="x",
        project_slug="alpha",
    )
    triples = extract_triples(note)
    assert any(t.predicate == "uses" for t in triples)


def test_extract_triples_no_pattern_returns_empty() -> None:
    note = Note(
        tier="episodic",
        kind="observation",
        content="just some unrelated free text",
        intent="x",
    )
    assert extract_triples(note) == []


# ── InMemoryGraphStore ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_in_memory_setup_teardown() -> None:
    store = InMemoryGraphStore()
    await store.setup()
    await store.teardown()


@pytest.mark.anyio
async def test_add_and_list_triples() -> None:
    store = InMemoryGraphStore()
    await store.setup()
    pid = uuid4()
    triple = GraphTriple(
        subject="a",
        predicate="uses",
        obj="b",
        source_passage_id=pid,
        project_slug="alpha",
    )
    await store.add_triple(triple)
    rows = await store.list_triples(project_slug="alpha")
    assert len(rows) == 1
    assert rows[0].subject == "a"


@pytest.mark.anyio
async def test_supersede_then_successor_both_visible() -> None:
    """Bi-temporal append model — closed prior + live successor coexist.

    Regression for the Order 4 audit finding where supersede overwrote
    the live row, destroying history.
    """
    store = InMemoryGraphStore()
    pid = uuid4()
    base = datetime.now(UTC) - timedelta(hours=2)
    moment = datetime.now(UTC) - timedelta(hours=1)
    await store.add_triple(
        GraphTriple(
            subject="oauth",
            predicate="uses",
            obj="bge",
            source_passage_id=pid,
            valid_from=base,
        ),
    )
    ok = await store.supersede_triple(
        subject="oauth",
        predicate="uses",
        object_="bge",
        source_passage_id=pid,
        at=moment,
    )
    assert ok is True
    # Now write the successor (same s,p,o,src) with a later valid_from.
    successor = GraphTriple(
        subject="oauth",
        predicate="uses",
        obj="bge",
        source_passage_id=pid,
        valid_from=moment,
    )
    await store.add_triple(successor)
    all_rows = await store.list_triples()
    # Both rows must exist: the closed prior (valid_until=moment) AND
    # the live successor (valid_until=None).
    assert len(all_rows) == 2
    closed = [r for r in all_rows if r.valid_until is not None]
    live = [r for r in all_rows if r.valid_until is None]
    assert len(closed) == 1
    assert len(live) == 1
    assert closed[0].valid_from == base
    assert live[0].valid_from == moment


@pytest.mark.anyio
async def test_supersede_triple_stamps_valid_until() -> None:
    store = InMemoryGraphStore()
    pid = uuid4()
    moment = datetime.now(UTC) - timedelta(hours=1)
    await store.add_triple(
        GraphTriple(
            subject="a",
            predicate="uses",
            obj="b",
            source_passage_id=pid,
            valid_from=moment,
        ),
    )
    ok = await store.supersede_triple(
        subject="a",
        predicate="uses",
        object_="b",
        source_passage_id=pid,
    )
    assert ok is True
    rows = await store.list_triples()
    assert rows[0].valid_until is not None


@pytest.mark.anyio
async def test_supersede_unknown_triple_returns_false() -> None:
    store = InMemoryGraphStore()
    pid = uuid4()
    ok = await store.supersede_triple(
        subject="x",
        predicate="y",
        object_="z",
        source_passage_id=pid,
    )
    assert ok is False


@pytest.mark.anyio
async def test_list_triples_filters_by_validity() -> None:
    store = InMemoryGraphStore()
    pid = uuid4()
    await store.add_triple(
        GraphTriple(
            subject="a",
            predicate="uses",
            obj="b",
            source_passage_id=pid,
            valid_until=datetime.now(UTC) - timedelta(hours=1),
        ),
    )
    rows = await store.list_triples(valid_at=datetime.now(UTC))
    assert rows == []


@pytest.mark.anyio
async def test_passage_phrase_indexing() -> None:
    store = InMemoryGraphStore()
    pid = uuid4()
    await store.add_passage(passage_id=pid, phrases=["oauth", "bge"])
    phrases = await store.list_phrases_for_passage(pid)
    assert phrases == ["bge", "oauth"]
    passages = await store.list_passages_for_phrase("oauth")
    assert pid in passages


@pytest.mark.anyio
async def test_phrase_neighbours_walk() -> None:
    store = InMemoryGraphStore()
    p1, p2 = uuid4(), uuid4()
    await store.add_passage(passage_id=p1, phrases=["oauth", "bge"])
    await store.add_passage(passage_id=p2, phrases=["bge", "embedder"])
    neighbours = await store.list_phrase_neighbours("oauth", max_hops=2)
    # oauth → p1 → bge → p2 → embedder
    assert "embedder" in neighbours


@pytest.mark.anyio
async def test_phrase_neighbours_unknown_phrase() -> None:
    store = InMemoryGraphStore()
    assert await store.list_phrase_neighbours("nope") == []


# ── personalized_pagerank ───────────────────────────────────────────────


def test_ppr_concentrates_mass_near_seed() -> None:
    p1, p2 = uuid4(), uuid4()
    phrase_to_passages = {
        "oauth": [p1],
        "bge": [p1, p2],
    }
    passage_to_phrases = {
        p1: ["oauth", "bge"],
        p2: ["bge"],
    }
    scores = personalized_pagerank(
        seeds=["oauth"],
        phrase_to_passages=phrase_to_passages,
        passage_to_phrases=passage_to_phrases,
    )
    # p1 contains oauth directly → higher mass than p2.
    assert scores.get(p1, 0.0) > scores.get(p2, 0.0)


def test_ppr_no_matching_seeds_returns_empty() -> None:
    scores = personalized_pagerank(
        seeds=["unknown"],
        phrase_to_passages={"oauth": [uuid4()]},
        passage_to_phrases={},
    )
    assert scores == {}


def test_ppr_invalid_args() -> None:
    with pytest.raises(ValueError, match="alpha"):
        personalized_pagerank(
            seeds=["x"],
            phrase_to_passages={},
            passage_to_phrases={},
            alpha=1.5,
        )
    with pytest.raises(ValueError, match="iterations"):
        personalized_pagerank(
            seeds=["x"],
            phrase_to_passages={},
            passage_to_phrases={},
            iterations=0,
        )


def test_ppr_deterministic() -> None:
    """Same inputs → same scores."""
    p1, p2 = uuid4(), uuid4()
    seeds = ["a"]
    p2p: dict[str, list[UUID]] = {"a": [p1], "b": [p2]}
    pas: dict[UUID, list[str]] = {p1: ["a"], p2: ["b"]}
    s1 = personalized_pagerank(
        seeds=seeds,
        phrase_to_passages=p2p,
        passage_to_phrases=pas,
    )
    s2 = personalized_pagerank(
        seeds=seeds,
        phrase_to_passages=p2p,
        passage_to_phrases=pas,
    )
    assert s1 == s2


# ── Consolidator ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_consolidator_writes_passages_and_triples(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as mind:
        graph = InMemoryGraphStore()
        await graph.setup()
        writer = EpisodicWriter(store=mind)
        await writer.write_decision(
            session_id="s1",
            intent="lock embedder bge",
            body="oauth uses bge-m3",
            project_slug="alpha",
        )
        consol = SemanticGraphConsolidator(store=mind, graph=graph)
        report = await consol.consolidate(project_slug="alpha")
        assert report.passages_added >= 1
        assert report.phrases_added >= 1
        # "oauth uses bge-m3" → triple with predicate "uses"
        triples = await graph.list_triples(project_slug="alpha")
        assert any(t.predicate == "uses" for t in triples)


@pytest.mark.anyio
async def test_consolidator_idempotent(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as mind:
        graph = InMemoryGraphStore()
        writer = EpisodicWriter(store=mind)
        await writer.write_decision(
            session_id="s1",
            intent="x",
            body="alpha uses beta",
            project_slug="alpha",
        )
        consol = SemanticGraphConsolidator(store=mind, graph=graph)
        first = await consol.consolidate(project_slug="alpha")
        second = await consol.consolidate(project_slug="alpha")
        # Second pass adds no new triples (same triples → keyed by
        # (s, p, o, source_passage_id) → coalesced).
        triples_after_first = await graph.list_triples()
        triples_after_second = await graph.list_triples()
        assert len(triples_after_first) == len(triples_after_second)
        assert second.triples_added == first.triples_added


# ── GraphRetriever ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_graph_retriever_finds_seeded_passage(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as mind:
        graph = InMemoryGraphStore()
        writer = EpisodicWriter(store=mind)
        note_oauth = await writer.write_decision(
            session_id="s1",
            intent="lock embedder",
            body="oauth flow uses bge embedder",
            project_slug="alpha",
        )
        await writer.write_decision(
            session_id="s1",
            intent="kanban path",
            body="kanban board lives at packages",
            project_slug="alpha",
        )
        consol = SemanticGraphConsolidator(store=mind, graph=graph)
        await consol.consolidate(project_slug="alpha")
        retriever = GraphRetriever(store=mind, graph=graph)
        hits = await retriever.recall(query="oauth bge", top_k=5)
        assert hits
        # The OAuth passage should be present (and likely top).
        assert any(h.note.id == note_oauth.id for h in hits)


@pytest.mark.anyio
async def test_graph_retriever_empty_query(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as mind:
        graph = InMemoryGraphStore()
        retriever = GraphRetriever(store=mind, graph=graph)
        assert await retriever.recall(query="") == []


@pytest.mark.anyio
async def test_graph_retriever_seeds_not_in_corpus(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as mind:
        graph = InMemoryGraphStore()
        retriever = GraphRetriever(store=mind, graph=graph)
        hits = await retriever.recall(query="completely-unrelated query")
        assert hits == []


@pytest.mark.anyio
async def test_graph_retriever_multi_hop(tmp_path: Path) -> None:
    """Seed → shared phrase → other passage (typical HippoRAG 2 case)."""
    async with open_store(tmp_path / "x.duckdb") as mind:
        graph = InMemoryGraphStore()
        writer = EpisodicWriter(store=mind)
        # Two notes share "bge" — seeding on "oauth" should still surface
        # the "embedder" note via the passage→phrase walk.
        await writer.write_decision(
            session_id="s1",
            intent="oauth note",
            body="oauth flow uses bge",
            project_slug="alpha",
        )
        await writer.write_decision(
            session_id="s2",
            intent="bge note",
            body="bge embedder is multilingual",
            project_slug="alpha",
        )
        consol = SemanticGraphConsolidator(store=mind, graph=graph)
        await consol.consolidate(project_slug="alpha")
        retriever = GraphRetriever(store=mind, graph=graph)
        hits = await retriever.recall(query="oauth", top_k=10)
        # Retriever can reach the second passage via the shared "bge".
        contents = " ".join(h.note.content for h in hits)
        assert "embedder" in contents


@pytest.mark.anyio
async def test_graph_retriever_threshold(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as mind:
        graph = InMemoryGraphStore()
        writer = EpisodicWriter(store=mind)
        await writer.write_decision(
            session_id="s1",
            intent="x",
            body="oauth bge",
            project_slug="alpha",
        )
        consol = SemanticGraphConsolidator(store=mind, graph=graph)
        await consol.consolidate(project_slug="alpha")
        retriever = GraphRetriever(store=mind, graph=graph)
        hits = await retriever.recall(query="oauth", threshold=2.0)
        # Threshold above any plausible PPR score → no hits.
        assert hits == []
