"""Tests for :mod:`selffork_mind.memory.tiers.episodic`.

Real DuckDB on tmp_path — no mocks. Validates per-round write,
deterministic dedup (UUID5 from content_hash), tag generation,
sentinel detection, decision write + supersession chain, embedder
hook, structured tool-call bypass, unicode, and orphan
(``project_slug=None``) sessions.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from selffork_mind.memory.tags import Tag, TagMatchMode
from selffork_mind.memory.tiers.episodic import (
    EpisodicToolCall,
    EpisodicWriter,
    detect_sentinels,
)
from selffork_mind.rag.embedder import EmbedderName, EmbeddingProvider
from selffork_mind.store import (
    DuckDBMindStore,
    RetrieveConfig,
    StoreScope,
)


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


# ── A deterministic local fake embedder so tests stay offline ─────────────


class _FakeEmbedder(EmbeddingProvider):
    """Cheap, deterministic 4-d embedder. No network, no model download."""

    def __init__(self, *, dim: int = 4) -> None:
        self._dim = dim

    @property
    def name(self) -> EmbedderName:
        return "ollama"  # closest neutral name in the EmbedderName Literal

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            # Hash the text bit-by-bit so two identical strings collide.
            seed = hash(text)
            vec = [
                ((seed >> i) & 1) * 1.0 - 0.5  # values in {-0.5, +0.5}
                for i in range(self._dim)
            ]
            out.append(vec)
        return out


# ── sentinel detection ────────────────────────────────────────────────────


def test_detect_sentinels_done_only() -> None:
    assert detect_sentinels("hello [SELFFORK:DONE] world") == ["[SELFFORK:DONE]"]


def test_detect_sentinels_spawn_prefix() -> None:
    sentinels = detect_sentinels("foo [SELFFORK:SPAWN: child-task] bar")
    assert sentinels == ["[SELFFORK:SPAWN:"]


def test_detect_sentinels_none() -> None:
    assert detect_sentinels("plain message, no sentinel here") == []


def test_detect_sentinels_both() -> None:
    text = "[SELFFORK:DONE] but also [SELFFORK:SPAWN: x]"
    sentinels = detect_sentinels(text)
    assert set(sentinels) == {"[SELFFORK:DONE]", "[SELFFORK:SPAWN:"}


# ── per-round write ────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_write_round_basic(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,
            operator_message="hadi devam edelim",
            cli_response="ok done",
        )
        assert len(notes) == 1
        note = notes[0]
        assert note.tier == "episodic"
        assert note.kind == "observation"
        assert "operator: hadi devam edelim" in note.content
        assert "cli: ok done" in note.content
        assert note.intent == "round 0"
        assert note.project_slug == "p1"
        assert note.session_id == "s1"
        assert note.source_pointer == "audit:s1:round:0"


@pytest.mark.anyio
async def test_write_round_dedup_via_content_hash(tmp_path: Path) -> None:
    """Same (tier, content_hash, session_id) → same UUID5 → upsert collapses."""
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        n1 = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,
            operator_message="msg",
            cli_response="resp",
        )
        n2 = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,  # same round
            operator_message="msg",
            cli_response="resp",
        )
        assert n1[0].id == n2[0].id


@pytest.mark.anyio
async def test_write_round_tags_observation(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=3,
            operator_message="hi",
            cli_response="ok",
        )
        tags = await store.list_tags(notes[0].id)
        as_pairs = {(t.key, t.value) for t in tags}
        assert ("project", "p1") in as_pairs
        assert ("session", "s1") in as_pairs
        assert ("cli", "claude-code") in as_pairs
        assert ("round", "3") in as_pairs
        assert ("kind", "observation") in as_pairs


@pytest.mark.anyio
async def test_write_round_orphan_no_project_tag(tmp_path: Path) -> None:
    """When project_slug is None, no `project` tag is attached."""
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        notes = await writer.write_round(
            session_id="s1",
            project_slug=None,
            cli_agent="opencode",
            round_index=0,
            operator_message="hello",
            cli_response="hi",
        )
        tags = await store.list_tags(notes[0].id)
        assert all(t.key != "project" for t in tags)
        assert any(t.key == "session" for t in tags)


@pytest.mark.anyio
async def test_write_round_sentinel_tags_and_importance(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,
            operator_message="finalising [SELFFORK:DONE]",
            cli_response="ack",
        )
        # Importance bumped for sentinel rounds (1.5 vs default 1.0)
        assert notes[0].importance == pytest.approx(1.5)
        tags = await store.list_tags(notes[0].id)
        assert ("sentinel", "[SELFFORK:DONE]") in {(t.key, t.value) for t in tags}


@pytest.mark.anyio
async def test_write_round_explicit_sentinels_override_detection(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,
            operator_message="totally clean",  # no sentinel literal
            cli_response="ack",
            sentinels=["[SELFFORK:SPAWN:"],
        )
        tags = await store.list_tags(notes[0].id)
        assert ("sentinel", "[SELFFORK:SPAWN:") in {(t.key, t.value) for t in tags}


@pytest.mark.anyio
async def test_write_round_unicode_content_round_trips(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,
            operator_message="naber dünyâ — Türkçe çıktısı",
            cli_response="şğç hello çekirdek",
        )
        fetched = await store.get_note(notes[0].id)
        assert fetched is not None
        assert "naber dünyâ" in fetched.content
        assert "şğç" in fetched.content


# ── tool-call bypass (Cognee 1:1 triple) ──────────────────────────────────


@pytest.mark.anyio
async def test_write_round_tool_call_creates_pattern_note(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        tc = EpisodicToolCall(
            tool="kanban_card_done",
            args={"card_id": "01H..."},
            status="ok",
            result_payload={"column_after": "done"},
        )
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=2,
            operator_message="işi bitir",
            cli_response="moved",
            tool_calls=[tc],
        )
        assert len(notes) == 2  # observation + 1 pattern
        assert notes[0].kind == "observation"
        assert notes[1].kind == "pattern"
        assert notes[1].intent == "tool:kanban_card_done"
        assert "kanban_card_done" in notes[1].content
        assert "ok" in notes[1].content
        assert notes[1].source_pointer == "audit:s1:round:2:tool:kanban_card_done"


@pytest.mark.anyio
async def test_write_round_tool_call_with_error(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        tc = EpisodicToolCall(
            tool="kanban_card_move",
            args={"card_id": "x", "to_column": "done"},
            status="invalid_args",
            error="card_id is required",
        )
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,
            operator_message="move",
            cli_response="failed",
            tool_calls=[tc],
        )
        pattern = notes[1]
        assert "card_id is required" in pattern.content


@pytest.mark.anyio
async def test_write_round_multiple_tool_calls_preserve_order(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        calls = [EpisodicToolCall(tool=f"t{i}", args={}, status="ok") for i in range(3)]
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,
            operator_message="m",
            cli_response="r",
            tool_calls=calls,
        )
        assert [n.intent for n in notes[1:]] == ["tool:t0", "tool:t1", "tool:t2"]


# ── decision flow ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_write_decision_basic(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        note = await writer.write_decision(
            session_id="s1",
            intent="use bge-m3",
            body="multilingual + small + Apache-2.0; default embedder",
            project_slug="p1",
            path_scope=("packages/mind/**/*.py",),
        )
        assert note.kind == "decision"
        assert note.intent == "use bge-m3"
        assert note.importance == 5.0
        assert note.path_scope == ("packages/mind/**/*.py",)


@pytest.mark.anyio
async def test_supersede_decision_bi_temporal_chain(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        old = await writer.write_decision(
            session_id="s1",
            intent="use bge-m3",
            body="multilingual + small",
            project_slug="p1",
        )
        old_updated, new = await writer.supersede_decision(
            note_id=old.id,
            new_intent="use jina-v3",
            new_body="multilingual + task-aware",
        )
        assert old_updated.id == old.id
        assert old_updated.valid_until is not None  # stamped
        assert new.id != old.id
        assert new.intent == "use jina-v3"
        assert new.kind == "decision"
        # Old fact is no longer "currently valid".
        assert not old_updated.is_currently_valid()
        assert new.is_currently_valid()


@pytest.mark.anyio
async def test_supersede_decision_unknown_id_raises(tmp_path: Path) -> None:
    from uuid import uuid4

    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        with pytest.raises(ValueError, match="not found"):
            await writer.supersede_decision(
                note_id=uuid4(),
                new_intent="x",
                new_body="y",
            )


@pytest.mark.anyio
async def test_supersede_decision_rejects_non_decision(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,
            operator_message="x",
            cli_response="y",
        )
        observation_id = notes[0].id
        with pytest.raises(ValueError, match="not a decision"):
            await writer.supersede_decision(
                note_id=observation_id,
                new_intent="i",
                new_body="b",
            )


# ── embedder integration ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_write_round_no_embedder_no_vector(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,
            operator_message="m",
            cli_response="r",
        )
        emb = await store.get_embedding(notes[0].id)
        assert emb is None


@pytest.mark.anyio
async def test_write_round_with_embedder_attaches_vector(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store, embedder=_FakeEmbedder(dim=4))
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,
            operator_message="m",
            cli_response="r",
        )
        emb = await store.get_embedding(notes[0].id)
        assert emb is not None
        vec, name = emb
        assert len(vec) == 4
        assert name == "ollama"  # the fake's ``name`` property


@pytest.mark.anyio
async def test_write_round_embeddings_for_all_notes(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store, embedder=_FakeEmbedder(dim=4))
        tc = EpisodicToolCall(tool="t", args={}, status="ok")
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,
            operator_message="m",
            cli_response="r",
            tool_calls=[tc],
        )
        # Both observation and pattern notes get embeddings.
        for note in notes:
            emb = await store.get_embedding(note.id)
            assert emb is not None


# ── retrieval integration check (smoke) ───────────────────────────────────


@pytest.mark.anyio
async def test_round_notes_retrievable_by_tag(tmp_path: Path) -> None:
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
        await writer.write_round(
            session_id="s2",
            project_slug="beta",
            cli_agent="opencode",
            round_index=0,
            operator_message="m",
            cli_response="r",
        )
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("episodic",),
                scope=StoreScope(project_slug="alpha"),
                tag_pairs=(("cli", "claude-code"),),
                tag_match_mode=TagMatchMode.ALL,
            ),
        )
        assert hits
        assert all(h.note.project_slug == "alpha" for h in hits)


@pytest.mark.anyio
async def test_decision_currently_valid_when_no_supersede(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        d = await writer.write_decision(
            session_id="s1",
            intent="lock",
            body="lock body",
            project_slug="p1",
        )
        # bi-temporal: lookup at "now" returns the live decision.
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("episodic",),
                scope=StoreScope(session_id="s1"),
                valid_at=datetime.now(d.valid_from.tzinfo) + timedelta(seconds=1),
            ),
        )
        assert any(h.note.id == d.id for h in hits)
        # And after supersede, that lookup no longer surfaces it.
        await writer.supersede_decision(
            note_id=d.id,
            new_intent="newer",
            new_body="newer body",
        )
        hits_after = await store.retrieve(
            RetrieveConfig(
                tiers=("episodic",),
                scope=StoreScope(session_id="s1"),
            ),
        )
        ids_after = {h.note.id for h in hits_after}
        assert d.id not in ids_after


# ── tag fixture sanity ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tag_now_helper_signature(tmp_path: Path) -> None:
    """Defensive: ``Tag.now`` semantics still work for our fixtures."""
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        notes = await writer.write_round(
            session_id="s1",
            project_slug="p1",
            cli_agent="claude-code",
            round_index=0,
            operator_message="m",
            cli_response="r",
        )
        # Detach a tag, confirm semantics
        ok = await store.detach_tag(note_id=notes[0].id, key="cli", value="claude-code")
        assert ok is True
        tags_after = await store.list_tags(notes[0].id)
        assert all(not (t.key == "cli" and t.value == "claude-code") for t in tags_after)
        # Reattach for completeness
        readded = await store.attach_tag(
            Tag.now(note_id=notes[0].id, key="cli", value="claude-code"),
        )
        assert readded.key == "cli"
