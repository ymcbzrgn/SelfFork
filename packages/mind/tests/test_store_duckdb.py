"""Tests for :mod:`selffork_mind.store.duckdb`.

Real DuckDB instances on tmp_path — no mocks (per ASLA MOCK YOK rule).

Uses an async context manager helper rather than a fixture to avoid the
event-loop ownership conflict between pytest-asyncio fixture cleanup and
pytest-anyio test execution. Each test gets a fresh, fully-set-up store
that tears down on exit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio
import pytest

from selffork_mind.memory.filters import (
    FilterAll,
    FilterAny,
    FilterCondition,
    FilterNot,
)
from selffork_mind.memory.model import Note
from selffork_mind.memory.tags import Tag, TagMatchMode
from selffork_mind.store import (
    DuckDBMindStore,
    RetrieveConfig,
    StoreScope,
)


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    """Open a fresh store, yield it, tear it down on exit."""
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


# ── setup / teardown ───────────────────────────────────────────────────────


class TestSetupTeardown:
    @pytest.mark.anyio
    async def test_setup_creates_db_file(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb"):
            assert (tmp_path / "mind.duckdb").is_file()

    @pytest.mark.anyio
    async def test_setup_idempotent(self, tmp_path: Path) -> None:
        s = DuckDBMindStore(db_path=tmp_path / "mind.duckdb")
        await s.setup()
        await s.setup()  # second call is a no-op
        await s.teardown()

    @pytest.mark.anyio
    async def test_teardown_idempotent(self, tmp_path: Path) -> None:
        s = DuckDBMindStore(db_path=tmp_path / "mind.duckdb")
        await s.setup()
        await s.teardown()
        await s.teardown()  # second call is a no-op

    @pytest.mark.anyio
    async def test_op_before_setup_raises(self, tmp_path: Path) -> None:
        s = DuckDBMindStore(db_path=tmp_path / "mind.duckdb")
        with pytest.raises(RuntimeError, match="not open"):
            await s.upsert_note(
                Note(tier="working", kind="observation", content="x"),
            )

    @pytest.mark.anyio
    async def test_db_persists_across_teardown_setup(self, tmp_path: Path) -> None:
        path = tmp_path / "mind.duckdb"
        async with open_store(path) as s:
            n = Note(
                tier="episodic",
                kind="observation",
                content="persistent",
                session_id="s1",
            )
            await s.upsert_note(n)
            note_id = n.id

        async with open_store(path) as s2:
            fetched = await s2.get_note(note_id)
            assert fetched is not None
            assert fetched.content == "persistent"


# ── upsert / get ───────────────────────────────────────────────────────────


class TestUpsertAndGet:
    @pytest.mark.anyio
    async def test_upsert_round_trips(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            n = Note(
                tier="episodic",
                kind="observation",
                content="Operator prefers Pydantic over dataclass",
                session_id="s1",
                project_slug="selffork",
            )
            await store.upsert_note(n)
            fetched = await store.get_note(n.id)
            assert fetched is not None
            assert fetched.content == n.content
            assert fetched.tier == "episodic"
            assert fetched.session_id == "s1"
            assert fetched.project_slug == "selffork"

    @pytest.mark.anyio
    async def test_upsert_idempotent_on_same_id(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            n = Note(tier="episodic", kind="observation", content="x", session_id="s1")
            await store.upsert_note(n)
            await store.upsert_note(n)  # second write must not error
            fetched = await store.get_note(n.id)
            assert fetched is not None

    @pytest.mark.anyio
    async def test_upsert_overrides_mutable_fields(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            n1 = Note(
                tier="episodic",
                kind="observation",
                content="x",
                session_id="s1",
                importance=1.0,
            )
            await store.upsert_note(n1)
            # Same identity (tier+content+session) → same id; new importance.
            n2 = n1.model_copy(update={"importance": 5.0})
            await store.upsert_note(n2)
            fetched = await store.get_note(n1.id)
            assert fetched is not None
            assert fetched.importance == 5.0

    @pytest.mark.anyio
    async def test_get_notes_returns_in_input_order(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            notes = [
                Note(tier="episodic", kind="observation", content=f"n{i}", session_id="s")
                for i in range(3)
            ]
            await store.upsert_notes(notes)
            ids = [n.id for n in notes]
            fetched = await store.get_notes(list(reversed(ids)))
            assert [f.id for f in fetched] == list(reversed(ids))

    @pytest.mark.anyio
    async def test_get_notes_skips_missing_silently(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            real = Note(
                tier="episodic",
                kind="observation",
                content="real",
                session_id="s",
            )
            ghost = Note(
                tier="episodic",
                kind="observation",
                content="ghost",
                session_id="s2",
            )
            await store.upsert_note(real)
            fetched = await store.get_notes([real.id, ghost.id])
            assert len(fetched) == 1
            assert fetched[0].id == real.id

    @pytest.mark.anyio
    async def test_missing_id_returns_none(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            n = Note(tier="working", kind="observation", content="x")
            fetched = await store.get_note(n.id)
            assert fetched is None

    @pytest.mark.anyio
    async def test_empty_get_notes_returns_empty(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            assert await store.get_notes([]) == []

    @pytest.mark.anyio
    async def test_empty_upsert_notes_returns_empty(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            assert await store.upsert_notes([]) == []

    @pytest.mark.anyio
    async def test_unicode_content_round_trips(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            n = Note(
                tier="episodic",
                kind="observation",
                content="Türkçe içerik 🚀 ı̇şlem ✓",
                session_id="s",
            )
            await store.upsert_note(n)
            fetched = await store.get_note(n.id)
            assert fetched is not None
            assert fetched.content == n.content

    @pytest.mark.anyio
    async def test_long_content_round_trips(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            payload = "x" * 100_000  # 100KB
            n = Note(
                tier="episodic",
                kind="observation",
                content=payload,
                session_id="s",
            )
            await store.upsert_note(n)
            fetched = await store.get_note(n.id)
            assert fetched is not None
            assert fetched.content == payload


# ── supersede (bi-temporal) ────────────────────────────────────────────────


class TestSupersede:
    @pytest.mark.anyio
    async def test_supersede_stamps_valid_until(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            n = Note(tier="semantic_graph", kind="decision", content="use BGE-M3")
            await store.upsert_note(n)
            moment = datetime.now(UTC)
            result = await store.supersede(n.id, at=moment)
            assert result is not None
            assert result.valid_until == moment

    @pytest.mark.anyio
    async def test_supersede_unknown_id_returns_none(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            n = Note(tier="working", kind="observation", content="x")
            result = await store.supersede(n.id)
            assert result is None

    @pytest.mark.anyio
    async def test_supersede_chain(self, tmp_path: Path) -> None:
        """A → superseded by B → superseded by C; all visible with include_invalid."""
        async with open_store(tmp_path / "mind.duckdb") as store:
            base = datetime.now(UTC) - timedelta(days=10)
            n_a = Note(
                tier="semantic_graph",
                kind="decision",
                content="OpenAI embeddings",
                valid_from=base,
            )
            n_b = Note(
                tier="semantic_graph",
                kind="decision",
                content="Jina embeddings",
                valid_from=base + timedelta(days=2),
            )
            n_c = Note(
                tier="semantic_graph",
                kind="decision",
                content="BGE-M3 embeddings",
                valid_from=base + timedelta(days=5),
            )
            await store.upsert_notes([n_a, n_b, n_c])
            await store.supersede(n_a.id, at=base + timedelta(days=2))
            await store.supersede(n_b.id, at=base + timedelta(days=5))

            current = await store.retrieve(
                RetrieveConfig(top_k=10, rerank_overfetch=1),
            )
            assert {h.note.id for h in current} == {n_c.id}

            historical = await store.retrieve(
                RetrieveConfig(top_k=10, rerank_overfetch=1, include_invalid=True),
            )
            assert {h.note.id for h in historical} == {n_a.id, n_b.id, n_c.id}

    @pytest.mark.anyio
    async def test_supersede_default_at_is_now(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            n = Note(
                tier="semantic_graph",
                kind="decision",
                content="x",
                valid_from=datetime.now(UTC) - timedelta(seconds=10),
            )
            await store.upsert_note(n)
            before = datetime.now(UTC)
            result = await store.supersede(n.id)
            after = datetime.now(UTC)
            assert result is not None
            assert result.valid_until is not None
            assert before <= result.valid_until <= after


# ── tags ──────────────────────────────────────────────────────────────────


class TestTags:
    @pytest.mark.anyio
    async def test_attach_and_list(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            n = Note(tier="episodic", kind="observation", content="x", session_id="s1")
            await store.upsert_note(n)
            await store.attach_tag(Tag.now(note_id=n.id, key="cli", value="claude-code"))
            await store.attach_tag(Tag.now(note_id=n.id, key="topic", value="mind"))
            tags = await store.list_tags(n.id)
            keys = {t.key for t in tags}
            assert keys == {"cli", "topic"}

    @pytest.mark.anyio
    async def test_attach_idempotent(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            n = Note(tier="episodic", kind="observation", content="x", session_id="s1")
            await store.upsert_note(n)
            tag = Tag.now(note_id=n.id, key="cli", value="claude-code")
            await store.attach_tag(tag)
            await store.attach_tag(tag)
            tags = await store.list_tags(n.id)
            assert len(tags) == 1

    @pytest.mark.anyio
    async def test_detach_returns_true_when_deleted(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            n = Note(tier="episodic", kind="observation", content="x", session_id="s1")
            await store.upsert_note(n)
            await store.attach_tag(Tag.now(note_id=n.id, key="cli", value="claude-code"))
            deleted = await store.detach_tag(
                note_id=n.id,
                key="cli",
                value="claude-code",
            )
            assert deleted is True
            deleted_again = await store.detach_tag(
                note_id=n.id,
                key="cli",
                value="claude-code",
            )
            assert deleted_again is False

    @pytest.mark.anyio
    async def test_attach_tags_empty_no_op(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            assert await store.attach_tags([]) == []

    @pytest.mark.anyio
    async def test_list_tags_for_unknown_note_empty(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            n = Note(tier="working", kind="observation", content="x")
            assert await store.list_tags(n.id) == []


# ── retrieve ──────────────────────────────────────────────────────────────


class TestRetrieve:
    @pytest.mark.anyio
    async def test_filter_by_tier(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(tier="episodic", kind="observation", content="e", session_id="s"),
                    Note(tier="procedural", kind="pattern", content="p"),
                ],
            )
            config = RetrieveConfig(tiers=("episodic",), top_k=10, rerank_overfetch=1)
            hits = await store.retrieve(config)
            assert {h.note.tier for h in hits} == {"episodic"}

    @pytest.mark.anyio
    async def test_scope_project(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(
                        tier="episodic",
                        kind="observation",
                        content="a",
                        project_slug="alpha",
                        session_id="s",
                    ),
                    Note(
                        tier="episodic",
                        kind="observation",
                        content="b",
                        project_slug="beta",
                        session_id="s",
                    ),
                ],
            )
            config = RetrieveConfig(
                scope=StoreScope(project_slug="alpha"),
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert {h.note.content for h in hits} == {"a"}

    @pytest.mark.anyio
    async def test_scope_session(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(tier="episodic", kind="observation", content="x", session_id="s1"),
                    Note(tier="episodic", kind="observation", content="y", session_id="s2"),
                ],
            )
            config = RetrieveConfig(
                scope=StoreScope(session_id="s1"),
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert {h.note.content for h in hits} == {"x"}

    @pytest.mark.anyio
    async def test_filter_dsl_and(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(tier="episodic", kind="decision", content="d1", session_id="s"),
                    Note(tier="episodic", kind="observation", content="o1", session_id="s"),
                    Note(tier="procedural", kind="decision", content="d2"),
                ],
            )
            config = RetrieveConfig(
                filter=FilterAll(
                    FilterCondition("tier", "eq", "episodic"),
                    FilterCondition("kind", "eq", "decision"),
                ),
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert [h.note.content for h in hits] == ["d1"]

    @pytest.mark.anyio
    async def test_filter_dsl_any_or(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(tier="episodic", kind="decision", content="x", session_id="s"),
                    Note(tier="episodic", kind="pattern", content="y", session_id="s"),
                    Note(tier="episodic", kind="observation", content="z", session_id="s"),
                ],
            )
            config = RetrieveConfig(
                filter=FilterAny(
                    FilterCondition("kind", "eq", "decision"),
                    FilterCondition("kind", "eq", "pattern"),
                ),
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert {h.note.content for h in hits} == {"x", "y"}

    @pytest.mark.anyio
    async def test_filter_dsl_not(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(
                        tier="episodic",
                        kind="decision",
                        content="pin",
                        session_id="s",
                        pinned=True,
                    ),
                    Note(
                        tier="episodic",
                        kind="decision",
                        content="nopin",
                        session_id="s",
                        pinned=False,
                    ),
                ],
            )
            config = RetrieveConfig(
                filter=FilterNot(FilterCondition("pinned", "eq", True)),
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert [h.note.content for h in hits] == ["nopin"]

    @pytest.mark.anyio
    async def test_filter_in(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(tier="episodic", kind="decision", content="d", session_id="s"),
                    Note(tier="episodic", kind="pattern", content="p", session_id="s"),
                    Note(tier="episodic", kind="observation", content="o", session_id="s"),
                ],
            )
            config = RetrieveConfig(
                filter=FilterCondition("kind", "in_", ["decision", "pattern"]),
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert {h.note.content for h in hits} == {"d", "p"}

    @pytest.mark.anyio
    async def test_filter_nin(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(tier="episodic", kind="decision", content="d", session_id="s"),
                    Note(tier="episodic", kind="pattern", content="p", session_id="s"),
                ],
            )
            config = RetrieveConfig(
                filter=FilterCondition("kind", "nin", ["decision"]),
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert {h.note.content for h in hits} == {"p"}

    @pytest.mark.anyio
    async def test_filter_contains(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(
                        tier="episodic",
                        kind="observation",
                        content="Operator picked Pydantic",
                        session_id="s",
                    ),
                    Note(
                        tier="episodic",
                        kind="observation",
                        content="dataclasses are fine too",
                        session_id="s",
                    ),
                ],
            )
            config = RetrieveConfig(
                filter=FilterCondition("content", "icontains", "PYDANTIC"),
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert any("Pydantic" in h.note.content for h in hits)
            assert all("dataclasses" not in h.note.content for h in hits)

    @pytest.mark.anyio
    async def test_bi_temporal_excludes_superseded(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            old = Note(
                tier="semantic_graph",
                kind="decision",
                content="default to OpenAI embeddings",
                valid_from=datetime.now(UTC) - timedelta(days=2),
            )
            await store.upsert_note(old)
            await store.supersede(old.id, at=datetime.now(UTC) - timedelta(days=1))
            config = RetrieveConfig(top_k=10, rerank_overfetch=1)
            hits = await store.retrieve(config)
            assert all(h.note.id != old.id for h in hits)

    @pytest.mark.anyio
    async def test_include_invalid_returns_superseded(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            old = Note(
                tier="semantic_graph",
                kind="decision",
                content="x",
                valid_from=datetime.now(UTC) - timedelta(days=2),
            )
            await store.upsert_note(old)
            await store.supersede(old.id, at=datetime.now(UTC) - timedelta(days=1))
            config = RetrieveConfig(top_k=10, rerank_overfetch=1, include_invalid=True)
            hits = await store.retrieve(config)
            assert any(h.note.id == old.id for h in hits)

    @pytest.mark.anyio
    async def test_pinned_sorts_first(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(
                        tier="working",
                        kind="observation",
                        content="recent",
                        importance=2.0,
                    ),
                    Note(
                        tier="working",
                        kind="observation",
                        content="pinned",
                        pinned=True,
                        importance=0.1,
                    ),
                ],
            )
            config = RetrieveConfig(top_k=10, rerank_overfetch=1)
            hits = await store.retrieve(config)
            assert hits[0].note.content == "pinned"

    @pytest.mark.anyio
    async def test_path_scope_glob_matches(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(
                        tier="procedural",
                        kind="pattern",
                        content="api-rule",
                        path_scope=("packages/orchestrator/**/*.py",),
                    ),
                    Note(
                        tier="procedural",
                        kind="pattern",
                        content="ui-rule",
                        path_scope=("apps/web/**/*.tsx",),
                    ),
                    Note(
                        tier="procedural",
                        kind="pattern",
                        content="global",
                        always_apply=True,
                    ),
                    Note(
                        tier="procedural",
                        kind="pattern",
                        content="unscoped",
                    ),
                ],
            )
            config = RetrieveConfig(
                top_k=10,
                rerank_overfetch=1,
                file_path="packages/orchestrator/src/cli.py",
            )
            hits = await store.retrieve(config)
            contents = {h.note.content for h in hits}
            assert "api-rule" in contents
            assert "global" in contents
            assert "unscoped" in contents  # empty path_scope = always match
            assert "ui-rule" not in contents

    @pytest.mark.anyio
    async def test_tag_match_any(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            notes = [
                Note(tier="episodic", kind="observation", content="a", session_id="s1"),
                Note(tier="episodic", kind="observation", content="b", session_id="s2"),
            ]
            await store.upsert_notes(notes)
            await store.attach_tags(
                [
                    Tag.now(note_id=notes[0].id, key="cli", value="claude-code"),
                    Tag.now(note_id=notes[1].id, key="cli", value="gemini-cli"),
                ],
            )
            config = RetrieveConfig(
                tag_pairs=(("cli", "claude-code"),),
                tag_match_mode=TagMatchMode.ANY,
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert {h.note.content for h in hits} == {"a"}

    @pytest.mark.anyio
    async def test_tag_match_all(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            notes = [
                Note(tier="episodic", kind="observation", content="a", session_id="s1"),
                Note(tier="episodic", kind="observation", content="b", session_id="s2"),
            ]
            await store.upsert_notes(notes)
            await store.attach_tags(
                [
                    Tag.now(note_id=notes[0].id, key="cli", value="claude-code"),
                    Tag.now(note_id=notes[0].id, key="topic", value="mind"),
                    Tag.now(note_id=notes[1].id, key="cli", value="claude-code"),
                ],
            )
            config = RetrieveConfig(
                tag_pairs=(("cli", "claude-code"), ("topic", "mind")),
                tag_match_mode=TagMatchMode.ALL,
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert {h.note.content for h in hits} == {"a"}

    @pytest.mark.anyio
    async def test_tag_match_any_multi_pair(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            notes = [
                Note(tier="episodic", kind="observation", content="a", session_id="s1"),
                Note(tier="episodic", kind="observation", content="b", session_id="s2"),
                Note(tier="episodic", kind="observation", content="c", session_id="s3"),
            ]
            await store.upsert_notes(notes)
            await store.attach_tags(
                [
                    Tag.now(note_id=notes[0].id, key="cli", value="claude-code"),
                    Tag.now(note_id=notes[1].id, key="cli", value="gemini-cli"),
                    # notes[2] has no tags
                ],
            )
            config = RetrieveConfig(
                tag_pairs=(
                    ("cli", "claude-code"),
                    ("cli", "gemini-cli"),
                ),
                tag_match_mode=TagMatchMode.ANY,
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert {h.note.content for h in hits} == {"a", "b"}

    @pytest.mark.anyio
    async def test_top_k_caps_results(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            # importance is clamped to [0.0, 10.0]; scale i down so 20 items
            # cover that range without violating the validator.
            notes = [
                Note(
                    tier="episodic",
                    kind="observation",
                    content=f"n{i:02d}",
                    session_id="s",
                    importance=i * 0.5,
                )
                for i in range(20)
            ]
            await store.upsert_notes(notes)
            config = RetrieveConfig(top_k=3, rerank_overfetch=1)
            hits = await store.retrieve(config)
            assert len(hits) == 3
            # importance decreasing → highest-importance content first
            assert [h.note.content for h in hits] == ["n19", "n18", "n17"]

    @pytest.mark.anyio
    async def test_rerank_overfetch_widens_candidates(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            # importance is clamped to [0.0, 10.0]; scale i down so 20 items
            # cover that range without violating the validator.
            notes = [
                Note(
                    tier="episodic",
                    kind="observation",
                    content=f"n{i:02d}",
                    session_id="s",
                    importance=i * 0.5,
                )
                for i in range(20)
            ]
            await store.upsert_notes(notes)
            config = RetrieveConfig(top_k=3, rerank_overfetch=4)
            hits = await store.retrieve(config)
            assert len(hits) == 12  # top_k * rerank_overfetch

    @pytest.mark.anyio
    async def test_empty_store_returns_empty(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            config = RetrieveConfig(top_k=10, rerank_overfetch=1)
            hits = await store.retrieve(config)
            assert hits == []


# ── concurrency ────────────────────────────────────────────────────────────


class TestConcurrency:
    @pytest.mark.anyio
    async def test_parallel_upserts_serialise_safely(self, tmp_path: Path) -> None:
        """Multiple concurrent upserts must not corrupt the DB."""
        async with open_store(tmp_path / "mind.duckdb") as store:
            notes = [
                Note(
                    tier="episodic",
                    kind="observation",
                    content=f"concurrent-{i}",
                    session_id=f"s{i}",
                )
                for i in range(20)
            ]

            async with anyio.create_task_group() as tg:
                for n in notes:
                    tg.start_soon(store.upsert_note, n)

            fetched = await store.get_notes([n.id for n in notes])
            assert len(fetched) == 20

    @pytest.mark.anyio
    async def test_parallel_retrieve_calls(self, tmp_path: Path) -> None:
        """Concurrent retrieves return consistent results."""
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(
                        tier="episodic",
                        kind="observation",
                        content=f"n{i}",
                        session_id="s",
                    )
                    for i in range(10)
                ],
            )
            results: list[int] = []

            async def query() -> None:
                hits = await store.retrieve(
                    RetrieveConfig(top_k=10, rerank_overfetch=1),
                )
                results.append(len(hits))

            async with anyio.create_task_group() as tg:
                for _ in range(8):
                    tg.start_soon(query)

            assert results == [10] * 8


# ── filter SQL builder ─────────────────────────────────────────────────────


class TestFilterToSQL:
    """Exercises the SQL builder corner cases through the public retrieve API."""

    @pytest.mark.anyio
    async def test_empty_all_returns_everything(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [
                    Note(tier="episodic", kind="observation", content="x", session_id="s"),
                    Note(tier="procedural", kind="pattern", content="y"),
                ],
            )
            config = RetrieveConfig(
                filter=FilterAll(),
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert len(hits) == 2

    @pytest.mark.anyio
    async def test_empty_any_returns_nothing(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [Note(tier="episodic", kind="observation", content="x", session_id="s")],
            )
            config = RetrieveConfig(
                filter=FilterAny(),
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert hits == []

    @pytest.mark.anyio
    async def test_in_with_empty_list_returns_nothing(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [Note(tier="episodic", kind="observation", content="x", session_id="s")],
            )
            config = RetrieveConfig(
                filter=FilterCondition("kind", "in_", []),
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert hits == []

    @pytest.mark.anyio
    async def test_nin_with_empty_list_returns_everything(self, tmp_path: Path) -> None:
        async with open_store(tmp_path / "mind.duckdb") as store:
            await store.upsert_notes(
                [Note(tier="episodic", kind="observation", content="x", session_id="s")],
            )
            config = RetrieveConfig(
                filter=FilterCondition("kind", "nin", []),
                top_k=10,
                rerank_overfetch=1,
            )
            hits = await store.retrieve(config)
            assert len(hits) == 1
