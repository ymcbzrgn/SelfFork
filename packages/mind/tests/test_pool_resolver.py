"""PoolResolver integration tests (ADR-009 §6 dual-pool query orchestration).

Cross-pool isolation, parallel queries, merge-by-score, and write-routing
are all verified against real DuckDB + LanceDB engines on tmp_path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from selffork_mind.memory.model import Note
from selffork_mind.store.base import (
    GLOBAL_GROUP_ID,
    PoolScope,
    RetrieveConfig,
)
from selffork_mind.store.lance import VectorEntry
from selffork_mind.store.pool import (
    PoolPaths,
    PoolResolver,
    default_global_pool_root,
    default_project_pool_root,
    default_selffork_home,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


_DIM = 8


def _vec(seed: int) -> tuple[float, ...]:
    return tuple(float((seed + i) % 5) / 5.0 for i in range(_DIM))


def _make_note(
    *,
    content: str,
    project_slug: str | None = None,
    group_id: str | None = None,
    tier: str = "episodic",
    session_id: str | None = "s1",
) -> Note:
    return Note(
        tier=tier,  # type: ignore[arg-type]
        kind="observation",
        content=content,
        project_slug=project_slug,
        group_id=group_id,
        session_id=session_id,
    )


@pytest.fixture
async def project_resolver(tmp_path: Path):
    resolver = PoolResolver(
        project_slug="test-project",
        home=tmp_path,
        embedding_dim=_DIM,
    )
    await resolver.setup()
    yield resolver
    await resolver.teardown()


@pytest.fixture
async def global_only_resolver(tmp_path: Path):
    resolver = PoolResolver(
        project_slug=None,
        home=tmp_path,
        embedding_dim=_DIM,
    )
    yield resolver
    await resolver.teardown()


class TestDefaultPaths:
    def test_selffork_home_env_override(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv("SELFFORK_HOME", str(tmp_path))
        assert default_selffork_home() == tmp_path.resolve()

    def test_selffork_home_default_is_home(self, monkeypatch) -> None:
        monkeypatch.delenv("SELFFORK_HOME", raising=False)
        result = default_selffork_home()
        assert result.name == ".selffork"

    def test_project_pool_root(self, tmp_path: Path) -> None:
        root = default_project_pool_root("foo", home=tmp_path)
        assert root == tmp_path / "projects" / "foo" / "mind"

    def test_project_pool_root_empty_slug_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="project_slug cannot be empty"):
            default_project_pool_root("", home=tmp_path)

    def test_global_pool_root(self, tmp_path: Path) -> None:
        root = default_global_pool_root(home=tmp_path)
        assert root == tmp_path / "global" / "mind"


class TestPoolPaths:
    def test_for_project(self, tmp_path: Path) -> None:
        paths = PoolPaths.for_project("foo", home=tmp_path)
        assert paths.notes_db == tmp_path / "projects" / "foo" / "mind" / "notes.duckdb"
        assert paths.vectors_dir == tmp_path / "projects" / "foo" / "mind" / "vectors.lance"

    def test_for_global(self, tmp_path: Path) -> None:
        paths = PoolPaths.for_global(home=tmp_path)
        assert paths.notes_db == tmp_path / "global" / "mind" / "notes.duckdb"
        assert paths.vectors_dir == tmp_path / "global" / "mind" / "vectors.lance"


class TestPoolResolverWrites:
    async def test_upsert_to_project_stamps_group_id(
        self,
        project_resolver: PoolResolver,
    ) -> None:
        note = _make_note(content="project fact", project_slug="test-project")
        result = await project_resolver.upsert_note(note, pool="project")
        assert result.group_id == "p:test-project"

    async def test_upsert_to_global_stamps_group_id(
        self,
        project_resolver: PoolResolver,
    ) -> None:
        note = _make_note(content="global fact", tier="reflection")
        result = await project_resolver.upsert_note(note, pool="global")
        assert result.group_id == GLOBAL_GROUP_ID

    async def test_upsert_to_project_without_slug_raises(
        self,
        global_only_resolver: PoolResolver,
    ) -> None:
        note = _make_note(content="x")
        with pytest.raises(RuntimeError, match="no project_slug"):
            await global_only_resolver.upsert_note(note, pool="project")

    async def test_upsert_to_global_works_without_slug(
        self,
        global_only_resolver: PoolResolver,
    ) -> None:
        note = _make_note(content="global only", tier="reflection")
        result = await global_only_resolver.upsert_note(note, pool="global")
        assert result.group_id == GLOBAL_GROUP_ID

    async def test_upsert_vector_routes_to_pool(
        self,
        project_resolver: PoolResolver,
    ) -> None:
        note_id = uuid4()
        # Write the metadata note first so the resolver has a target;
        # vector_entry then mirrors it.
        await project_resolver.upsert_note(
            _make_note(content="vec test", project_slug="test-project"),
            pool="project",
        )
        entry = VectorEntry(
            note_id=note_id,
            group_id="WILL_BE_OVERWRITTEN",
            project_slug="test-project",
            session_id="s1",
            tier="episodic",
            vector=_vec(0),
            content_hash="hash",
            written_at=datetime.now(UTC),
        )
        await project_resolver.upsert_vector(entry, pool="project")
        # Vector should be in the PROJECT pool's LanceDB with group_id stamped.
        project_engines = project_resolver._project
        assert project_engines is not None
        hits = await project_engines.vectors.query(
            _vec(0),
            group_ids=("p:test-project",),
            top_k=5,
        )
        assert any(h.note_id == note_id for h in hits)


class TestPoolResolverRetrieve:
    async def test_project_only_scope_returns_project_hits(
        self,
        project_resolver: PoolResolver,
    ) -> None:
        await project_resolver.upsert_note(
            _make_note(content="proj fact", project_slug="test-project"),
            pool="project",
        )
        await project_resolver.upsert_note(
            _make_note(content="global fact", tier="reflection"),
            pool="global",
        )
        hits = await project_resolver.retrieve(
            pool_scope=PoolScope(project_slug="test-project"),
            config=RetrieveConfig(top_k=10),
        )
        contents = {h.note.content for h in hits}
        assert "proj fact" in contents
        assert "global fact" not in contents

    async def test_global_only_scope_returns_global_hits(
        self,
        project_resolver: PoolResolver,
    ) -> None:
        await project_resolver.upsert_note(
            _make_note(content="proj fact", project_slug="test-project"),
            pool="project",
        )
        await project_resolver.upsert_note(
            _make_note(content="global fact", tier="reflection"),
            pool="global",
        )
        hits = await project_resolver.retrieve(
            pool_scope=PoolScope(include_global=True),
            config=RetrieveConfig(top_k=10),
        )
        contents = {h.note.content for h in hits}
        assert "global fact" in contents
        assert "proj fact" not in contents

    async def test_cross_pool_scope_unions(
        self,
        project_resolver: PoolResolver,
    ) -> None:
        await project_resolver.upsert_note(
            _make_note(content="proj fact", project_slug="test-project"),
            pool="project",
        )
        await project_resolver.upsert_note(
            _make_note(content="global fact", tier="reflection"),
            pool="global",
        )
        hits = await project_resolver.retrieve(
            pool_scope=PoolScope(project_slug="test-project", include_global=True),
            config=RetrieveConfig(top_k=10),
        )
        contents = {h.note.content for h in hits}
        assert {"proj fact", "global fact"} <= contents

    async def test_empty_scope_returns_empty(
        self,
        project_resolver: PoolResolver,
    ) -> None:
        # PoolScope() — no project, no global → no engines targeted.
        hits = await project_resolver.retrieve(
            pool_scope=PoolScope(),
            config=RetrieveConfig(top_k=10),
        )
        assert hits == []

    async def test_top_k_caps_merged_result(
        self,
        project_resolver: PoolResolver,
    ) -> None:
        for i in range(5):
            await project_resolver.upsert_note(
                _make_note(content=f"p{i}", project_slug="test-project"),
                pool="project",
            )
        for i in range(5):
            await project_resolver.upsert_note(
                _make_note(content=f"g{i}", tier="reflection"),
                pool="global",
            )
        hits = await project_resolver.retrieve(
            pool_scope=PoolScope(project_slug="test-project", include_global=True),
            config=RetrieveConfig(top_k=3),
        )
        assert len(hits) == 3


class TestVectorCrossPool:
    async def test_cross_pool_vector_query(
        self,
        project_resolver: PoolResolver,
    ) -> None:
        # Seed both pools with distinguishable vectors.
        p_id = uuid4()
        g_id = uuid4()
        await project_resolver.upsert_vector(
            VectorEntry(
                note_id=p_id,
                group_id="ignored",
                project_slug="test-project",
                session_id="s1",
                tier="episodic",
                vector=_vec(0),
                content_hash="p",
            ),
            pool="project",
        )
        await project_resolver.upsert_vector(
            VectorEntry(
                note_id=g_id,
                group_id="ignored",
                project_slug=None,
                session_id=None,
                tier="reflection",
                vector=_vec(0),
                content_hash="g",
            ),
            pool="global",
        )

        cross = await project_resolver.query_vectors(
            _vec(0),
            pool_scope=PoolScope(project_slug="test-project", include_global=True),
            top_k=10,
        )
        ids = {h.note_id for h in cross}
        assert {p_id, g_id} <= ids
        # Stable rank: scores descending.
        scores = [h.score for h in cross]
        assert scores == sorted(scores, reverse=True)

    async def test_project_vector_query_excludes_global(
        self,
        project_resolver: PoolResolver,
    ) -> None:
        p_id = uuid4()
        g_id = uuid4()
        await project_resolver.upsert_vector(
            VectorEntry(
                note_id=p_id,
                group_id="ignored",
                project_slug="test-project",
                session_id="s1",
                tier="episodic",
                vector=_vec(0),
                content_hash="p",
            ),
            pool="project",
        )
        await project_resolver.upsert_vector(
            VectorEntry(
                note_id=g_id,
                group_id="ignored",
                project_slug=None,
                session_id=None,
                tier="reflection",
                vector=_vec(0),
                content_hash="g",
            ),
            pool="global",
        )

        project_hits = await project_resolver.query_vectors(
            _vec(0),
            pool_scope=PoolScope(project_slug="test-project"),
            top_k=10,
        )
        ids = {h.note_id for h in project_hits}
        assert p_id in ids
        assert g_id not in ids


class TestPoolIsolation:
    """Filesystem-level: project deletion must not affect global pool."""

    async def test_pools_use_separate_directories(self, tmp_path: Path) -> None:
        resolver = PoolResolver(
            project_slug="iso-test",
            home=tmp_path,
            embedding_dim=_DIM,
        )
        await resolver.setup()
        try:
            await resolver.upsert_note(
                _make_note(content="project", project_slug="iso-test"),
                pool="project",
            )
            await resolver.upsert_note(
                _make_note(content="global", tier="reflection"),
                pool="global",
            )

            project_paths = PoolPaths.for_project("iso-test", home=tmp_path)
            global_paths = PoolPaths.for_global(home=tmp_path)

            assert project_paths.notes_db.exists()
            assert global_paths.notes_db.exists()
            assert project_paths.notes_db != global_paths.notes_db
            # Parent directories are different — `rm -rf projects/<slug>`
            # cannot touch global.
            assert project_paths.notes_db.parent != global_paths.notes_db.parent
        finally:
            await resolver.teardown()

    async def test_two_projects_isolated(self, tmp_path: Path) -> None:
        r1 = PoolResolver(project_slug="proj-a", home=tmp_path, embedding_dim=_DIM)
        r2 = PoolResolver(project_slug="proj-b", home=tmp_path, embedding_dim=_DIM)
        await r1.setup()
        await r2.setup()
        try:
            await r1.upsert_note(
                _make_note(content="a only", project_slug="proj-a"),
                pool="project",
            )
            await r2.upsert_note(
                _make_note(content="b only", project_slug="proj-b"),
                pool="project",
            )
            hits_a = await r1.retrieve(
                pool_scope=PoolScope(project_slug="proj-a"),
                config=RetrieveConfig(top_k=10),
            )
            hits_b = await r2.retrieve(
                pool_scope=PoolScope(project_slug="proj-b"),
                config=RetrieveConfig(top_k=10),
            )
            assert {h.note.content for h in hits_a} == {"a only"}
            assert {h.note.content for h in hits_b} == {"b only"}
        finally:
            await r1.teardown()
            await r2.teardown()


class TestBackwardCompatibility:
    """Existing PROJECT data without group_id must coalesce to p:<slug>."""

    async def test_legacy_row_without_group_id_matched(
        self,
        tmp_path: Path,
    ) -> None:
        # Write directly via DuckDBMindStore with group_id=None, then verify
        # that PoolResolver finds it through coalesce(group_id, p:<slug>).
        resolver = PoolResolver(
            project_slug="legacy-proj",
            home=tmp_path,
            embedding_dim=_DIM,
        )
        await resolver.setup()
        try:
            engines = resolver._project
            assert engines is not None
            legacy_note = Note(
                tier="episodic",
                kind="observation",
                content="legacy fact",
                project_slug="legacy-proj",
                # group_id intentionally None (simulates pre-ADR-009 data)
                group_id=None,
            )
            await engines.notes.upsert_note(legacy_note)
            # Now lookup via PoolResolver with PoolScope — should find it
            # via coalesce path.
            hits = await resolver.retrieve(
                pool_scope=PoolScope(project_slug="legacy-proj"),
                config=RetrieveConfig(top_k=10),
            )
            contents = {h.note.content for h in hits}
            assert "legacy fact" in contents
        finally:
            await resolver.teardown()


class TestTeardownIdempotent:
    async def test_teardown_after_setup(self, tmp_path: Path) -> None:
        resolver = PoolResolver(
            project_slug="td-test",
            home=tmp_path,
            embedding_dim=_DIM,
        )
        await resolver.setup()
        await resolver.teardown()
        # Second teardown should be a no-op (no engines open).
        await resolver.teardown()

    async def test_teardown_without_setup(self, tmp_path: Path) -> None:
        resolver = PoolResolver(
            project_slug="td-test",
            home=tmp_path,
            embedding_dim=_DIM,
        )
        # No setup called — teardown must not raise.
        await resolver.teardown()


class TestUUIDInRowToNote:
    """Round-trip Note id ↔ DuckDB UUID column with group_id."""

    async def test_round_trip_preserves_id(
        self,
        project_resolver: PoolResolver,
    ) -> None:
        note = _make_note(content="round-trip", project_slug="test-project")
        stored = await project_resolver.upsert_note(note, pool="project")
        hits = await project_resolver.retrieve(
            pool_scope=PoolScope(project_slug="test-project"),
            config=RetrieveConfig(top_k=10),
        )
        # The returned note's id must round-trip through DuckDB.
        ids = {h.note.id for h in hits}
        assert isinstance(stored.id, UUID)
        assert stored.id in ids
