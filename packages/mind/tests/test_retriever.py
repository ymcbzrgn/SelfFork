"""Tests for :class:`HybridRetriever` and :mod:`selffork_mind.rag.scoring`.

Real DuckDB store + deterministic local embedder/reranker — no mocks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from selffork_mind.memory.filters import FilterCondition
from selffork_mind.memory.model import Note
from selffork_mind.memory.tags import Tag, TagMatchMode
from selffork_mind.projections.provenance import ProvenanceRecorder
from selffork_mind.rag.embedder import EmbedderName, EmbeddingProvider
from selffork_mind.rag.reranker import RerankerName, RerankerProvider
from selffork_mind.rag.retriever import (
    HybridRetriever,
    classify_query,
)
from selffork_mind.rag.scoring import (
    BM25Scorer,
    ConvexFusionScorer,
    SemanticScorer,
    TagBoostScorer,
    tokenize,
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


# ── Deterministic offline test backends ───────────────────────────────────


class _BagOfWordsEmbedder(EmbeddingProvider):
    """4-d bag-of-words embedder over a fixed token set.

    Maps each text to a vector counting occurrences of the four anchor
    tokens — enough to give meaningfully different cosine values for the
    test corpora below without spinning up sentence-transformers.
    """

    _ANCHORS: tuple[str, ...] = ("oauth", "kanban", "embedder", "graph")

    @property
    def name(self) -> EmbedderName:
        return "ollama"

    @property
    def dimension(self) -> int:
        return len(self._ANCHORS)

    @property
    def supports_multilingual(self) -> bool:
        return True

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._encode(t) for t in texts]

    def _encode(self, text: str) -> list[float]:
        tokens = tokenize(text)
        return [float(tokens.count(anchor)) for anchor in self._ANCHORS]


class _AlphabeticalReranker(RerankerProvider):
    """Reranker that scores by alphabetical position — deterministic."""

    @property
    def name(self) -> RerankerName:
        return "bge-rerank-v2-m3"

    async def rerank(
        self,
        query: str,
        candidates: Sequence[str],
    ) -> list[float]:
        del query
        # Higher score for documents that come earlier alphabetically.
        return [1.0 / (1 + sorted(candidates).index(d)) for d in candidates]


# ── helpers ────────────────────────────────────────────────────────────────


async def _seed_corpus(store: DuckDBMindStore) -> dict[str, Note]:
    notes_data: dict[str, Note] = {}
    for kind, content, intent in [
        ("decision", "OAuth flow uses bge-m3 embedder", "lock oauth embedder"),
        ("observation", "Kanban card moved to done by claude-code", "kanban event"),
        ("pattern", "Tool: kanban_card_done; status=ok", "kanban tool"),
        (
            "decision",
            "Graph backend Kuzu lands in Order 4",
            "graph backend choice",
        ),
    ]:
        note = Note(
            tier="episodic",
            kind=kind,  # type: ignore[arg-type]
            content=content,
            intent=intent,
            project_slug="alpha",
            session_id="s1",
        )
        stored = await store.upsert_note(note)
        notes_data[intent] = stored
    return notes_data


async def _attach_dummy_tags(store: DuckDBMindStore, notes: dict[str, Note]) -> None:
    pairs = [
        ("lock oauth embedder", [("kind", "decision"), ("topic", "embedder")]),
        ("kanban event", [("cli", "claude-code"), ("topic", "kanban")]),
        ("kanban tool", [("cli", "claude-code"), ("topic", "kanban")]),
        ("graph backend choice", [("kind", "decision"), ("topic", "graph")]),
    ]
    tags: list[Tag] = []
    for intent, kvs in pairs:
        nid = notes[intent].id
        for k, v in kvs:
            tags.append(Tag.now(note_id=nid, key=k, value=v))
    await store.attach_tags(tags)


async def _attach_embeddings(
    store: DuckDBMindStore,
    notes: dict[str, Note],
    embedder: _BagOfWordsEmbedder,
) -> None:
    items = list(notes.items())
    vectors = await embedder.embed([n.content for _, n in items])
    for (_intent, note), vec in zip(items, vectors, strict=True):
        await store.attach_embedding(
            note_id=note.id,
            vector=vec,
            embedder_name=embedder.name,
        )


# ── tokenize ──────────────────────────────────────────────────────────────


def test_tokenize_lowercases_and_splits() -> None:
    assert tokenize("OAuth FLOW uses bge-m3") == ["oauth", "flow", "uses", "bge", "m3"]


def test_tokenize_unicode_turkish() -> None:
    assert tokenize("naber dünyâ — şğç") == ["naber", "dünyâ", "şğç"]


# ── classify_query ────────────────────────────────────────────────────────


def test_classify_query_vector_default() -> None:
    assert classify_query("OAuth flow karari nedir") == "vector"


def test_classify_query_temporal_keyword_routes_hybrid() -> None:
    assert classify_query("when did we supersede the embedder") == "hybrid"


def test_classify_query_turkish_temporal_keyword() -> None:
    assert classify_query("Dün ne kararı verdik?") == "hybrid"


# ── Scorers ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_bm25_scorer_ranks_lexical_overlap_first(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        scorer = BM25Scorer()
        candidates = list(notes.values())
        scores = scorer.score(
            query="oauth embedder",
            query_embedding=None,
            candidates=candidates,
        )
        # The OAuth note should outrank the graph note for an OAuth query.
        oauth_id = notes["lock oauth embedder"].id
        graph_id = notes["graph backend choice"].id
        assert scores[oauth_id] > scores[graph_id]


@pytest.mark.anyio
async def test_bm25_scorer_empty_query_returns_zeros(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        scorer = BM25Scorer()
        scores = scorer.score(
            query="   ",
            query_embedding=None,
            candidates=list(notes.values()),
        )
        assert all(v == 0.0 for v in scores.values())


@pytest.mark.anyio
async def test_bm25_scorer_empty_corpus(tmp_path: Path) -> None:
    del tmp_path
    scorer = BM25Scorer()
    assert scorer.score(query="x", query_embedding=None, candidates=[]) == {}


@pytest.mark.anyio
async def test_tag_boost_scorer_counts_matches(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        await _attach_dummy_tags(store, notes)
        scorer = TagBoostScorer()
        oauth_id = notes["lock oauth embedder"].id
        kanban_id = notes["kanban event"].id
        per_note_tags = {
            oauth_id: {("kind", "decision"), ("topic", "embedder")},
            kanban_id: {("cli", "claude-code"), ("topic", "kanban")},
        }
        scores = scorer.score(
            query="x",
            query_embedding=None,
            candidates=[notes["lock oauth embedder"], notes["kanban event"]],
            tag_pairs=(("kind", "decision"),),
            tag_pairs_per_note=per_note_tags,
        )
        assert scores[oauth_id] == 1.0
        assert scores[kanban_id] == 0.0


@pytest.mark.anyio
async def test_semantic_scorer_passes_through(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        scorer = SemanticScorer()
        # Fake a per-note vector score
        first = next(iter(notes.values()))
        scores = scorer.score(
            query="x",
            query_embedding=None,
            candidates=list(notes.values()),
            per_note_vector_score={first.id: 0.91},
        )
        assert scores[first.id] == 0.91


# ── ConvexFusionScorer ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_convex_fusion_combines_components(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        await _attach_dummy_tags(store, notes)
        scorer = ConvexFusionScorer.build_default()

        candidates = list(notes.values())
        # Provide vector scores so the semantic component contributes.
        vector_scores = {n.id: float(i) / len(candidates) for i, n in enumerate(candidates)}
        per_tag = {n.id: {("kind", "decision")} for n in candidates}

        scores = scorer.score(
            query="oauth embedder",
            query_embedding=None,
            candidates=candidates,
            per_note_vector_score=vector_scores,
            tag_pairs=(("kind", "decision"),),
            tag_pairs_per_note=per_tag,
        )
        # Convex sum stays in [0, 1] when each component normalises.
        assert all(0.0 <= s <= 1.0 + 1e-9 for s in scores.values())


@pytest.mark.anyio
async def test_convex_fusion_constant_component_contributes_zero(tmp_path: Path) -> None:
    """A scorer that returns constants → min-max normalises to 0 → contributes 0."""
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        scorer = ConvexFusionScorer.build_default()
        candidates = list(notes.values())
        # Constant vector scores; BM25 still varies.
        vector_scores = {n.id: 0.5 for n in candidates}
        scores = scorer.score(
            query="oauth",
            query_embedding=None,
            candidates=candidates,
            per_note_vector_score=vector_scores,
        )
        # OAuth note should still rank top because BM25 ≠ flat.
        oauth_id = notes["lock oauth embedder"].id
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        assert ranked[0][0] == oauth_id


def test_convex_fusion_rejects_empty_components() -> None:
    with pytest.raises(ValueError, match="at least one component"):
        ConvexFusionScorer([])


# ── HybridRetriever ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_recall_empty_store_returns_empty(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        retriever = HybridRetriever(store=store, embedder=_BagOfWordsEmbedder())
        hits = await retriever.recall(query="anything")
        assert hits == []


@pytest.mark.anyio
async def test_recall_vector_path_ranks_oauth_first(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        embedder = _BagOfWordsEmbedder()
        await _attach_embeddings(store, notes, embedder)
        retriever = HybridRetriever(store=store, embedder=embedder)
        hits = await retriever.recall(query="oauth bge", top_k=4)
        assert hits
        assert hits[0].note.id == notes["lock oauth embedder"].id


@pytest.mark.anyio
async def test_recall_threshold_cuts_low_scores(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        embedder = _BagOfWordsEmbedder()
        await _attach_embeddings(store, notes, embedder)
        retriever = HybridRetriever(store=store, embedder=embedder)
        hits = await retriever.recall(query="oauth", threshold=0.99, top_k=10)
        # With threshold near 1, only the strongest matches survive.
        assert all(h.score >= 0.99 for h in hits)


@pytest.mark.anyio
async def test_recall_top_k_cap(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        embedder = _BagOfWordsEmbedder()
        await _attach_embeddings(store, notes, embedder)
        retriever = HybridRetriever(store=store, embedder=embedder)
        hits = await retriever.recall(query="oauth", top_k=2)
        assert len(hits) <= 2


@pytest.mark.anyio
async def test_recall_scope_filters_other_project(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes_alpha = await _seed_corpus(store)
        del notes_alpha
        embedder = _BagOfWordsEmbedder()
        # Add a beta-project note that mentions oauth too.
        beta = Note(
            tier="episodic",
            kind="decision",
            content="OAuth flow in beta uses jina",
            intent="beta oauth",
            project_slug="beta",
            session_id="s2",
        )
        beta_stored = await store.upsert_note(beta)
        vec = await embedder.embed([beta.content])
        await store.attach_embedding(
            note_id=beta_stored.id,
            vector=vec[0],
            embedder_name=embedder.name,
        )

        retriever = HybridRetriever(store=store, embedder=embedder)
        hits = await retriever.recall(
            query="oauth",
            scope=StoreScope(project_slug="alpha"),
            top_k=10,
        )
        assert all(h.note.project_slug == "alpha" for h in hits)


@pytest.mark.anyio
async def test_recall_filter_excludes_kinds(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        embedder = _BagOfWordsEmbedder()
        await _attach_embeddings(store, notes, embedder)
        retriever = HybridRetriever(store=store, embedder=embedder)
        hits = await retriever.recall(
            query="kanban",
            filter=FilterCondition("kind", "eq", "decision"),
            top_k=10,
        )
        assert all(h.note.kind == "decision" for h in hits)


@pytest.mark.anyio
async def test_recall_tag_match_any_with_boost(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        await _attach_dummy_tags(store, notes)
        embedder = _BagOfWordsEmbedder()
        await _attach_embeddings(store, notes, embedder)
        retriever = HybridRetriever(store=store, embedder=embedder)
        hits = await retriever.recall(
            query="topic decision",
            tag_pairs=(("kind", "decision"),),
            tag_match_mode=TagMatchMode.ANY,
            top_k=10,
        )
        assert hits
        assert all(h.note.kind == "decision" for h in hits)


@pytest.mark.anyio
async def test_recall_tag_match_all_strict(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        await _attach_dummy_tags(store, notes)
        embedder = _BagOfWordsEmbedder()
        await _attach_embeddings(store, notes, embedder)
        retriever = HybridRetriever(store=store, embedder=embedder)
        hits = await retriever.recall(
            query="x",
            tag_pairs=(("cli", "claude-code"), ("topic", "kanban")),
            tag_match_mode=TagMatchMode.ALL,
            top_k=10,
        )
        # Only the kanban observation/pattern carry both tags.
        kanban_event = notes["kanban event"].id
        kanban_tool = notes["kanban tool"].id
        ids = {h.note.id for h in hits}
        assert ids == {kanban_event, kanban_tool}


@pytest.mark.anyio
async def test_recall_tier_filter_only_episodic(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        embedder = _BagOfWordsEmbedder()
        await _attach_embeddings(store, notes, embedder)
        # Add a procedural note (different tier) to verify filtering.
        proc = Note(
            tier="procedural",
            kind="pattern",
            content="oauth procedural",
            intent="proc",
            project_slug="alpha",
            session_id="s1",
        )
        proc_stored = await store.upsert_note(proc)
        vec = await embedder.embed([proc.content])
        await store.attach_embedding(
            note_id=proc_stored.id,
            vector=vec[0],
            embedder_name=embedder.name,
        )
        retriever = HybridRetriever(store=store, embedder=embedder)
        hits = await retriever.recall(
            query="oauth",
            tiers=("episodic",),
            top_k=10,
        )
        assert all(h.note.tier == "episodic" for h in hits)


@pytest.mark.anyio
async def test_recall_file_path_scope_filters_unrelated(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        embedder = _BagOfWordsEmbedder()
        # Two notes; one scoped to packages/mind, one to packages/orchestrator.
        scoped = Note(
            tier="episodic",
            kind="decision",
            content="oauth in mind package",
            intent="mind oauth",
            project_slug="alpha",
            session_id="s1",
            path_scope=("packages/mind/**/*.py",),
        )
        unscoped = Note(
            tier="episodic",
            kind="decision",
            content="oauth in orchestrator package",
            intent="orch oauth",
            project_slug="alpha",
            session_id="s1",
            path_scope=("packages/orchestrator/**/*.py",),
        )
        s1 = await store.upsert_note(scoped)
        s2 = await store.upsert_note(unscoped)
        for note in (s1, s2):
            vec = await embedder.embed([note.content])
            await store.attach_embedding(
                note_id=note.id,
                vector=vec[0],
                embedder_name=embedder.name,
            )
        retriever = HybridRetriever(store=store, embedder=embedder)
        hits = await retriever.recall(
            query="oauth",
            file_path="packages/mind/src/file.py",
            top_k=10,
        )
        ids = {h.note.id for h in hits}
        assert s1.id in ids
        # Path-scope is best-effort glob; either way the orchestrator-only note
        # is filtered when file_path matches mind.
        assert s2.id not in ids


@pytest.mark.anyio
async def test_recall_records_provenance(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        embedder = _BagOfWordsEmbedder()
        await _attach_embeddings(store, notes, embedder)
        log_path = tmp_path / "provenance.jsonl"
        recorder = ProvenanceRecorder(log_path=log_path)
        retriever = HybridRetriever(
            store=store,
            embedder=embedder,
            provenance=recorder,
        )
        await retriever.recall(
            query="oauth",
            top_k=2,
            correlation_id="corr-1",
            session_id="s1",
            project_slug="alpha",
        )
        assert log_path.is_file()
        entries = recorder.read_all()
        assert len(entries) == 1
        e = entries[0]
        assert e.correlation_id == "corr-1"
        assert e.session_id == "s1"
        assert e.project_slug == "alpha"
        assert e.query == "oauth"
        assert e.retriever.startswith("vector:")
        assert len(e.note_ids) <= 2


@pytest.mark.anyio
async def test_recall_records_provenance_even_when_no_hits(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        log_path = tmp_path / "provenance.jsonl"
        recorder = ProvenanceRecorder(log_path=log_path)
        retriever = HybridRetriever(
            store=store,
            embedder=_BagOfWordsEmbedder(),
            provenance=recorder,
        )
        await retriever.recall(
            query="anything",
            session_id="s",
            correlation_id="c",
        )
        entries = recorder.read_all()
        assert len(entries) == 1
        assert entries[0].note_ids == ()


@pytest.mark.anyio
async def test_recall_with_reranker_replaces_fusion_score(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        embedder = _BagOfWordsEmbedder()
        await _attach_embeddings(store, notes, embedder)
        retriever = HybridRetriever(
            store=store,
            embedder=embedder,
            reranker=_AlphabeticalReranker(),
        )
        hits = await retriever.recall(query="oauth", top_k=4)
        # Alphabetical reranker → all scores are 1/(rank+1), monotone non-increasing.
        scores = [h.score for h in hits]
        assert scores == sorted(scores, reverse=True)


@pytest.mark.anyio
async def test_recall_no_embedder_runs_without_query_embedding(tmp_path: Path) -> None:
    """Embedder=None still works (BM25-only fallback)."""
    async with open_store(tmp_path / "x.duckdb") as store:
        notes = await _seed_corpus(store)
        await _attach_dummy_tags(store, notes)
        retriever = HybridRetriever(store=store, embedder=None)
        hits = await retriever.recall(query="oauth", top_k=4)
        assert hits  # BM25 alone surfaces matches.


@pytest.mark.anyio
async def test_recall_route_classification_in_provenance(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        log_path = tmp_path / "provenance.jsonl"
        recorder = ProvenanceRecorder(log_path=log_path)
        retriever = HybridRetriever(
            store=store,
            embedder=_BagOfWordsEmbedder(),
            provenance=recorder,
        )
        await retriever.recall(query="when did we change embedder", session_id="s")
        entries = recorder.read_all()
        assert entries[0].retriever.startswith("hybrid:")


@pytest.mark.anyio
async def test_recall_correlation_id_propagates(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        log_path = tmp_path / "provenance.jsonl"
        recorder = ProvenanceRecorder(log_path=log_path)
        retriever = HybridRetriever(
            store=store,
            embedder=_BagOfWordsEmbedder(),
            provenance=recorder,
        )
        await retriever.recall(
            query="x",
            correlation_id="abc-123",
            session_id="s",
        )
        assert recorder.read_all()[0].correlation_id == "abc-123"


# ── Embedder property surface ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_recall_embedder_dim_carries_through(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        retriever = HybridRetriever(store=store, embedder=_BagOfWordsEmbedder())
        assert retriever.embedder is not None
        assert retriever.embedder.dimension == 4
