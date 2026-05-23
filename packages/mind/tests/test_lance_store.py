"""LanceDBVectorStore integration tests (Apache 2.0 dep installed).

ADR-009 §2 dual-pool partitioning via group_id column verified end-to-end:
- Setup creates the table directory.
- upsert_vector + upsert_vectors round-trip.
- query with group_ids filter isolates one pool's rows.
- count by group_id reflects partitioned write.
- delete removes a specific note_id row.
- merge_insert upserts (note_id is the conflict key).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from selffork_mind.store.lance import LanceDBVectorStore, VectorEntry

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


_DIM = 8


def _vec(seed: int) -> tuple[float, ...]:
    # Deterministic small-dim vectors; rng-free so the test is reproducible.
    base = [float((seed + i) % 5) / 5.0 for i in range(_DIM)]
    return tuple(base)


@pytest.fixture
async def lance_store(tmp_path: Path):
    store = LanceDBVectorStore(
        db_path=tmp_path / "vectors.lance",
        embedding_dim=_DIM,
    )
    await store.setup()
    yield store
    await store.teardown()


class TestSetupTeardown:
    async def test_setup_creates_directory(self, tmp_path: Path) -> None:
        store = LanceDBVectorStore(db_path=tmp_path / "v.lance", embedding_dim=_DIM)
        await store.setup()
        try:
            # LanceDB creates the dir on first table create.
            assert store.db_path.parent.exists()
        finally:
            await store.teardown()

    async def test_setup_idempotent(self, tmp_path: Path) -> None:
        store = LanceDBVectorStore(db_path=tmp_path / "v.lance", embedding_dim=_DIM)
        await store.setup()
        await store.setup()  # second call should be a no-op
        await store.teardown()

    async def test_invalid_embedding_dim_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="embedding_dim must be positive"):
            LanceDBVectorStore(db_path=tmp_path / "v.lance", embedding_dim=0)

    async def test_query_before_setup_raises(self, tmp_path: Path) -> None:
        store = LanceDBVectorStore(db_path=tmp_path / "v.lance", embedding_dim=_DIM)
        with pytest.raises(RuntimeError, match="not open"):
            await store.query(_vec(0))


class TestVectorWrites:
    async def test_upsert_single(self, lance_store: LanceDBVectorStore) -> None:
        entry = VectorEntry(
            note_id=uuid4(),
            group_id="p:test",
            project_slug="test",
            session_id="s1",
            tier="episodic",
            vector=_vec(1),
            content_hash="abc",
            written_at=datetime.now(UTC),
        )
        await lance_store.upsert_vector(entry)
        assert await lance_store.count() == 1

    async def test_upsert_batch(self, lance_store: LanceDBVectorStore) -> None:
        entries = [
            VectorEntry(
                note_id=uuid4(),
                group_id="p:test",
                project_slug="test",
                session_id="s1",
                tier="episodic",
                vector=_vec(i),
                content_hash=f"h{i}",
            )
            for i in range(5)
        ]
        await lance_store.upsert_vectors(entries)
        assert await lance_store.count() == 5

    async def test_upsert_empty_is_noop(self, lance_store: LanceDBVectorStore) -> None:
        await lance_store.upsert_vectors([])
        assert await lance_store.count() == 0

    async def test_vector_dim_mismatch_raises(
        self,
        lance_store: LanceDBVectorStore,
    ) -> None:
        bad = VectorEntry(
            note_id=uuid4(),
            group_id="p:test",
            project_slug="test",
            session_id="s1",
            tier="episodic",
            vector=(1.0, 2.0),  # too short
            content_hash="x",
        )
        with pytest.raises(ValueError, match="vector dim mismatch"):
            await lance_store.upsert_vector(bad)

    async def test_merge_insert_updates_on_note_id(
        self,
        lance_store: LanceDBVectorStore,
    ) -> None:
        note_id = uuid4()
        first = VectorEntry(
            note_id=note_id,
            group_id="p:test",
            project_slug="test",
            session_id="s1",
            tier="episodic",
            vector=_vec(0),
            content_hash="v1",
        )
        await lance_store.upsert_vector(first)
        assert await lance_store.count() == 1

        # Same note_id, different content_hash + vector → update (not duplicate).
        second = VectorEntry(
            note_id=note_id,
            group_id="p:test",
            project_slug="test",
            session_id="s1",
            tier="episodic",
            vector=_vec(3),
            content_hash="v2",
        )
        await lance_store.upsert_vector(second)
        assert await lance_store.count() == 1


class TestQuery:
    async def test_query_returns_nearest(
        self,
        lance_store: LanceDBVectorStore,
    ) -> None:
        target = VectorEntry(
            note_id=uuid4(),
            group_id="p:test",
            project_slug="test",
            session_id="s1",
            tier="episodic",
            vector=_vec(0),
            content_hash="match",
        )
        distractor = VectorEntry(
            note_id=uuid4(),
            group_id="p:test",
            project_slug="test",
            session_id="s1",
            tier="episodic",
            vector=_vec(7),
            content_hash="miss",
        )
        await lance_store.upsert_vectors([target, distractor])

        hits = await lance_store.query(_vec(0), top_k=2)
        assert len(hits) == 2
        # Nearest (the inserted "match") should rank first.
        assert hits[0].note_id == target.note_id
        assert hits[0].score >= hits[1].score

    async def test_query_dim_mismatch_raises(
        self,
        lance_store: LanceDBVectorStore,
    ) -> None:
        with pytest.raises(ValueError, match="query_vector dim mismatch"):
            await lance_store.query((1.0, 2.0), top_k=5)


class TestDualPoolPartitioning:
    """ADR-009 §1: group_id column isolates PROJECT and GLOBAL pool rows."""

    async def test_group_id_filter_returns_only_matching(
        self,
        lance_store: LanceDBVectorStore,
    ) -> None:
        project_entry = VectorEntry(
            note_id=uuid4(),
            group_id="p:selffork",
            project_slug="selffork",
            session_id="s1",
            tier="episodic",
            vector=_vec(0),
            content_hash="proj",
        )
        global_entry = VectorEntry(
            note_id=uuid4(),
            group_id="g:global",
            project_slug=None,
            session_id=None,
            tier="reflection",
            vector=_vec(0),  # same vector to ensure both are "near"
            content_hash="glob",
        )
        await lance_store.upsert_vectors([project_entry, global_entry])

        project_hits = await lance_store.query(
            _vec(0),
            group_ids=("p:selffork",),
            top_k=10,
        )
        global_hits = await lance_store.query(
            _vec(0),
            group_ids=("g:global",),
            top_k=10,
        )
        cross_hits = await lance_store.query(
            _vec(0),
            group_ids=("p:selffork", "g:global"),
            top_k=10,
        )

        assert {h.note_id for h in project_hits} == {project_entry.note_id}
        assert {h.note_id for h in global_hits} == {global_entry.note_id}
        assert {h.note_id for h in cross_hits} == {project_entry.note_id, global_entry.note_id}

    async def test_count_by_group_id(self, lance_store: LanceDBVectorStore) -> None:
        await lance_store.upsert_vectors(
            [
                VectorEntry(
                    note_id=uuid4(),
                    group_id="p:a",
                    project_slug="a",
                    session_id=None,
                    tier="episodic",
                    vector=_vec(i),
                    content_hash=f"a{i}",
                )
                for i in range(3)
            ]
            + [
                VectorEntry(
                    note_id=uuid4(),
                    group_id="g:global",
                    project_slug=None,
                    session_id=None,
                    tier="reflection",
                    vector=_vec(i),
                    content_hash=f"g{i}",
                )
                for i in range(2)
            ],
        )
        assert await lance_store.count() == 5
        assert await lance_store.count(group_id="p:a") == 3
        assert await lance_store.count(group_id="g:global") == 2

    async def test_tier_filter(self, lance_store: LanceDBVectorStore) -> None:
        await lance_store.upsert_vectors(
            [
                VectorEntry(
                    note_id=uuid4(),
                    group_id="p:test",
                    project_slug="test",
                    session_id=None,
                    tier="episodic",
                    vector=_vec(0),
                    content_hash="e",
                ),
                VectorEntry(
                    note_id=uuid4(),
                    group_id="p:test",
                    project_slug="test",
                    session_id=None,
                    tier="reflection",
                    vector=_vec(0),
                    content_hash="r",
                ),
            ],
        )
        episodic_hits = await lance_store.query(_vec(0), tier="episodic", top_k=10)
        reflection_hits = await lance_store.query(_vec(0), tier="reflection", top_k=10)
        assert len(episodic_hits) == 1
        assert episodic_hits[0].tier == "episodic"
        assert len(reflection_hits) == 1
        assert reflection_hits[0].tier == "reflection"


class TestDelete:
    async def test_delete_removes_row(self, lance_store: LanceDBVectorStore) -> None:
        keep_id = uuid4()
        gone_id = uuid4()
        await lance_store.upsert_vectors(
            [
                VectorEntry(
                    note_id=keep_id,
                    group_id="p:test",
                    project_slug="test",
                    session_id=None,
                    tier="episodic",
                    vector=_vec(0),
                    content_hash="keep",
                ),
                VectorEntry(
                    note_id=gone_id,
                    group_id="p:test",
                    project_slug="test",
                    session_id=None,
                    tier="episodic",
                    vector=_vec(2),
                    content_hash="gone",
                ),
            ],
        )
        assert await lance_store.count() == 2
        await lance_store.delete(gone_id)
        assert await lance_store.count() == 1
        remaining = await lance_store.query(_vec(0), top_k=10)
        assert {h.note_id for h in remaining} == {keep_id}
