"""Tests for L1-L3 compaction strategies + apply_plan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from selffork_mind.compaction import (
    ImportanceDistiller,
    MedoidClusterCompactor,
    RecencyDecayCompactor,
    apply_plan,
)
from selffork_mind.memory.model import Note
from selffork_mind.store import DuckDBMindStore, RetrieveConfig, StoreScope


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


# ── L1 Recency-decay ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_recency_empty_window() -> None:
    plan = await RecencyDecayCompactor().plan(notes=[])
    assert plan.is_empty()


@pytest.mark.anyio
async def test_recency_pinned_unchanged() -> None:
    note = Note(
        tier="working",
        kind="pointer",
        content="x",
        intent="x",
        pinned=True,
        importance=10.0,
        valid_from=datetime.now(UTC) - timedelta(days=14),
    )
    plan = await RecencyDecayCompactor().plan(notes=[note])
    assert not plan.importance_updates


@pytest.mark.anyio
async def test_recency_decay_applies_to_old_notes() -> None:
    old = Note(
        tier="episodic",
        kind="observation",
        content="old",
        intent="x",
        importance=5.0,
        valid_from=datetime.now(UTC) - timedelta(days=14),
    )
    fresh = Note(
        tier="episodic",
        kind="observation",
        content="fresh",
        intent="x",
        importance=5.0,
    )
    plan = await RecencyDecayCompactor(half_life_seconds=7 * 24 * 3600).plan(
        notes=[old, fresh],
    )
    # 14 days = 2 half-lives → 5.0 * 0.25 = 1.25
    decayed_for_old = next(
        (u for u in plan.importance_updates if u.note_id == old.id),
        None,
    )
    assert decayed_for_old is not None
    assert decayed_for_old.new_importance == pytest.approx(1.25, abs=0.01)


@pytest.mark.anyio
async def test_recency_floor_applied() -> None:
    very_old = Note(
        tier="episodic",
        kind="observation",
        content="ancient",
        intent="x",
        importance=5.0,
        valid_from=datetime.now(UTC) - timedelta(days=365),
    )
    plan = await RecencyDecayCompactor(floor=0.05).plan(notes=[very_old])
    update = plan.importance_updates[0]
    assert update.new_importance >= 0.05


def test_recency_invalid_constructor_args() -> None:
    with pytest.raises(ValueError, match="half_life_seconds"):
        RecencyDecayCompactor(half_life_seconds=0)
    with pytest.raises(ValueError, match="floor"):
        RecencyDecayCompactor(floor=1.0, ceiling=0.5)


# ── L2 Importance distillation ───────────────────────────────────────────


@pytest.mark.anyio
async def test_distill_bumps_decisions() -> None:
    decision = Note(
        tier="episodic",
        kind="decision",
        content="lock embedder bge",
        intent="lock",
        importance=2.0,
    )
    plan = await ImportanceDistiller(decision_bump=2.0).plan(notes=[decision])
    assert any(
        u.note_id == decision.id and u.new_importance == 4.0 for u in plan.importance_updates
    )


@pytest.mark.anyio
async def test_distill_recognises_decision_token_in_intent() -> None:
    note = Note(
        tier="episodic",
        kind="observation",
        content="x",
        intent="we picked option A",
        importance=2.0,
    )
    plan = await ImportanceDistiller(decision_bump=1.5).plan(notes=[note])
    assert plan.importance_updates


@pytest.mark.anyio
async def test_distill_evicts_low_importance_episodic() -> None:
    low = Note(
        tier="episodic",
        kind="observation",
        content="x",
        intent="trivial",
        importance=0.05,
    )
    plan = await ImportanceDistiller(evict_threshold=0.1).plan(notes=[low])
    assert low.id in plan.supersede_ids


@pytest.mark.anyio
async def test_distill_no_evict_for_procedural() -> None:
    """L2 only evicts episodic/working — never procedural/semantic/etc."""
    proc = Note(
        tier="procedural",
        kind="pattern",
        content="pat",
        intent="trivial",
        importance=0.01,
    )
    plan = await ImportanceDistiller(evict_threshold=0.1).plan(notes=[proc])
    assert proc.id not in plan.supersede_ids


@pytest.mark.anyio
async def test_distill_pinned_immune() -> None:
    pinned = Note(
        tier="episodic",
        kind="observation",
        content="x",
        intent="trivial",
        importance=0.01,
        pinned=True,
    )
    plan = await ImportanceDistiller().plan(notes=[pinned])
    assert pinned.id not in plan.supersede_ids


def test_distill_invalid_args() -> None:
    with pytest.raises(ValueError, match="decision_bump"):
        ImportanceDistiller(decision_bump=1.0)


# ── L3 Medoid clustering ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_cluster_too_few_notes(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        compactor = MedoidClusterCompactor(store=store)
        plan = await compactor.plan(notes=[])
        assert plan.is_empty()


@pytest.mark.anyio
async def test_cluster_jaccard_groups_near_dup(tmp_path: Path) -> None:
    """Two near-identical notes (high Jaccard) → one cluster."""
    async with open_store(tmp_path / "x.duckdb") as store:
        a = Note(
            tier="episodic",
            kind="observation",
            content="oauth flow uses bge-m3 embedder",
            intent="oauth",
        )
        b = Note(
            tier="episodic",
            kind="observation",
            content="oauth flow uses bge-m3 embedder for production",
            intent="oauth",
        )
        c = Note(
            tier="episodic",
            kind="observation",
            content="kanban board lives at packages",
            intent="kanban",
        )
        await store.upsert_notes([a, b, c])
        compactor = MedoidClusterCompactor(store=store, distance_cutoff=0.5)
        plan = await compactor.plan(notes=[a, b, c])
        assert plan.clusters
        members = {m for cl in plan.clusters for m in cl.member_ids}
        assert a.id in members
        assert b.id in members
        assert c.id not in members


@pytest.mark.anyio
async def test_cluster_pinned_excluded(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        a = Note(
            tier="episodic",
            kind="observation",
            content="dup content",
            intent="x",
            pinned=True,
        )
        b = Note(
            tier="episodic",
            kind="observation",
            content="dup content other",
            intent="x",
        )
        await store.upsert_notes([a, b])
        compactor = MedoidClusterCompactor(store=store, distance_cutoff=0.5)
        plan = await compactor.plan(notes=[a, b])
        for cluster in plan.clusters:
            assert a.id not in cluster.member_ids


@pytest.mark.anyio
async def test_cluster_uses_vectors_when_present(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        a = Note(tier="episodic", kind="observation", content="A", intent="a")
        b = Note(tier="episodic", kind="observation", content="B", intent="b")
        await store.upsert_notes([a, b])
        # Identical embeddings → cosine distance 0 → cluster
        for note in (a, b):
            await store.attach_embedding(
                note_id=note.id,
                vector=[1.0, 0.0, 0.0, 0.0],
                embedder_name="ollama",
            )
        compactor = MedoidClusterCompactor(store=store, distance_cutoff=0.1)
        plan = await compactor.plan(notes=[a, b])
        assert plan.clusters
        assert plan.summary["distance_mode"] == "vector"


def test_cluster_invalid_args(tmp_path: Path) -> None:
    """Construction-time validation — no event loop needed."""
    del tmp_path
    with pytest.raises(ValueError, match="distance_cutoff"):
        MedoidClusterCompactor(store=object(), distance_cutoff=2.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="min_cluster_size"):
        MedoidClusterCompactor(store=object(), min_cluster_size=1)  # type: ignore[arg-type]


# ── apply_plan ────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_apply_plan_updates_importance(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        note = Note(
            tier="episodic",
            kind="observation",
            content="x",
            intent="x",
            importance=2.0,
        )
        stored = await store.upsert_note(note)
        plan = await ImportanceDistiller(decision_bump=2.0).plan(
            notes=[
                stored.model_copy(update={"intent": "lock embedder", "kind": "decision"}),
            ],
        )
        counts = await apply_plan(plan, store=store, notes=[stored])
        assert counts["importance_updates"] >= 1
        refreshed = await store.get_note(stored.id)
        assert refreshed is not None
        # importance bumped
        assert refreshed.importance != stored.importance


@pytest.mark.anyio
async def test_apply_plan_supersedes_evicted(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        note = Note(
            tier="episodic",
            kind="observation",
            content="x",
            intent="trivial",
            importance=0.05,
        )
        stored = await store.upsert_note(note)
        plan = await ImportanceDistiller(evict_threshold=0.1).plan(notes=[stored])
        counts = await apply_plan(plan, store=store, notes=[stored])
        assert counts["supersede"] >= 1
        # Currently-valid retrieval no longer surfaces the evicted note.
        hits = await store.retrieve(RetrieveConfig(tiers=("episodic",)))
        assert all(h.note.id != stored.id for h in hits)


@pytest.mark.anyio
async def test_apply_plan_supersedes_cluster_non_reps(tmp_path: Path) -> None:
    async with open_store(tmp_path / "x.duckdb") as store:
        a = Note(
            tier="episodic",
            kind="observation",
            content="oauth flow uses bge",
            intent="x",
        )
        b = Note(
            tier="episodic",
            kind="observation",
            content="oauth flow uses bge embedder",
            intent="x",
        )
        await store.upsert_notes([a, b])
        compactor = MedoidClusterCompactor(store=store, distance_cutoff=0.5)
        plan = await compactor.plan(notes=[a, b])
        counts = await apply_plan(plan, store=store, notes=[a, b])
        assert counts["clusters_applied"] >= 1
        # One representative survives in the currently-valid window.
        hits = await store.retrieve(
            RetrieveConfig(
                tiers=("episodic",),
                scope=StoreScope(),
            ),
        )
        assert len(hits) == 1
