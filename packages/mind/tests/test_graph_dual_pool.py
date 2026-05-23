"""ADR-009 §3 T3 Semantic Graph PROJECT/GLOBAL split tests.

Physical isolation: each pool carries its own SemanticGraphStore instance
inside :class:`~selffork_mind.store.pool._PoolEngines`. Cross-pool queries
fan out via ``PoolResolver.list_triples`` and merge with deterministic
ordering.

GraphTriple.group_id is stamped at write time by the resolver so triples
keep their pool provenance even when merged into a cross-pool result list.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from selffork_mind.graph.base import GraphTriple
from selffork_mind.store.base import GLOBAL_GROUP_ID, PoolScope
from selffork_mind.store.pool import PoolResolver

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _triple(
    *,
    subject: str = "operator",
    predicate: str = "prefers",
    obj: str = "minimalist_ui",
    project_slug: str | None = "proj-a",
    confidence: float = 1.0,
    valid_from: datetime | None = None,
) -> GraphTriple:
    return GraphTriple(
        subject=subject,
        predicate=predicate,
        obj=obj,
        source_passage_id=uuid4(),
        project_slug=project_slug,
        confidence=confidence,
        valid_from=valid_from or datetime.now(UTC) - timedelta(minutes=1),
    )


@pytest.fixture
async def resolver(tmp_path: Path):
    r = PoolResolver(project_slug="proj-a", home=tmp_path, embedding_dim=8)
    await r.setup()
    yield r
    await r.teardown()


class TestGraphTripleSchema:
    def test_group_id_default_none(self) -> None:
        t = _triple()
        assert t.group_id is None

    def test_explicit_group_id_set(self) -> None:
        t = GraphTriple(
            subject="s",
            predicate="p",
            obj="o",
            source_passage_id=uuid4(),
            group_id="g:global",
        )
        assert t.group_id == "g:global"

    def test_payload_includes_group_id(self) -> None:
        t = GraphTriple(
            subject="s",
            predicate="p",
            obj="o",
            source_passage_id=uuid4(),
            group_id="p:foo",
        )
        payload = t.to_payload()
        assert payload["group_id"] == "p:foo"


class TestProjectPoolGraph:
    async def test_add_triple_to_project_stamps_group_id(
        self,
        resolver: PoolResolver,
    ) -> None:
        triple = _triple(project_slug="proj-a")
        await resolver.add_triple(triple, pool="project")

        triples = await resolver.list_triples(
            pool_scope=PoolScope(project_slug="proj-a"),
        )
        assert len(triples) == 1
        assert triples[0].group_id == "p:proj-a"

    async def test_project_isolated_from_global(
        self,
        resolver: PoolResolver,
    ) -> None:
        await resolver.add_triple(_triple(subject="project_fact"), pool="project")
        await resolver.add_triple(
            _triple(subject="global_fact", project_slug=None),
            pool="global",
        )

        project_only = await resolver.list_triples(
            pool_scope=PoolScope(project_slug="proj-a"),
        )
        global_only = await resolver.list_triples(
            pool_scope=PoolScope(include_global=True),
        )

        assert {t.subject for t in project_only} == {"project_fact"}
        assert {t.subject for t in global_only} == {"global_fact"}


class TestGlobalPoolGraph:
    async def test_add_triple_to_global_stamps_group_id(
        self,
        resolver: PoolResolver,
    ) -> None:
        triple = _triple(subject="operator_identity", project_slug=None)
        await resolver.add_triple(triple, pool="global")

        triples = await resolver.list_triples(
            pool_scope=PoolScope(include_global=True),
        )
        assert len(triples) == 1
        assert triples[0].group_id == GLOBAL_GROUP_ID

    async def test_global_only_resolver_no_project(self, tmp_path: Path) -> None:
        r = PoolResolver(project_slug=None, home=tmp_path, embedding_dim=8)
        try:
            triple = _triple(subject="g_only", project_slug=None)
            await r.add_triple(triple, pool="global")
            triples = await r.list_triples(
                pool_scope=PoolScope(include_global=True),
            )
            assert len(triples) == 1
            assert triples[0].group_id == GLOBAL_GROUP_ID
        finally:
            await r.teardown()


class TestCrossPoolGraphQuery:
    async def test_include_global_unions_triples(
        self,
        resolver: PoolResolver,
    ) -> None:
        # Two triples per pool — different subjects so they don't collide.
        for i in range(2):
            await resolver.add_triple(
                _triple(subject=f"project_{i}"),
                pool="project",
            )
            await resolver.add_triple(
                _triple(subject=f"global_{i}", project_slug=None),
                pool="global",
            )

        cross = await resolver.list_triples(
            pool_scope=PoolScope(project_slug="proj-a", include_global=True),
        )
        subjects = {t.subject for t in cross}
        assert subjects == {"project_0", "project_1", "global_0", "global_1"}

    async def test_merged_results_deterministically_ordered(
        self,
        resolver: PoolResolver,
    ) -> None:
        await resolver.add_triple(
            _triple(subject="z_project", predicate="p1"),
            pool="project",
        )
        await resolver.add_triple(
            _triple(subject="a_global", project_slug=None, predicate="p1"),
            pool="global",
        )
        merged = await resolver.list_triples(
            pool_scope=PoolScope(project_slug="proj-a", include_global=True),
        )
        # Sorted by (subject, predicate, obj, source_passage_id).
        subjects = [t.subject for t in merged]
        assert subjects == sorted(subjects)

    async def test_predicate_filter_applied_per_pool(
        self,
        resolver: PoolResolver,
    ) -> None:
        await resolver.add_triple(
            _triple(subject="x", predicate="P1"),
            pool="project",
        )
        await resolver.add_triple(
            _triple(subject="y", project_slug=None, predicate="P2"),
            pool="global",
        )

        p1_only = await resolver.list_triples(
            pool_scope=PoolScope(project_slug="proj-a", include_global=True),
            predicate="P1",
        )
        assert {t.subject for t in p1_only} == {"x"}

        p2_only = await resolver.list_triples(
            pool_scope=PoolScope(project_slug="proj-a", include_global=True),
            predicate="P2",
        )
        assert {t.subject for t in p2_only} == {"y"}

    async def test_empty_scope_returns_empty(
        self,
        resolver: PoolResolver,
    ) -> None:
        result = await resolver.list_triples(pool_scope=PoolScope())
        assert result == []


class TestSupersedePreservesGroupId:
    """audit-god finding #1 regression — supersede must not drop group_id."""

    async def test_supersede_keeps_group_id(self, resolver: PoolResolver) -> None:
        source_id = uuid4()
        live = GraphTriple(
            subject="operator",
            predicate="prefers",
            obj="minimalist_ui",
            source_passage_id=source_id,
            project_slug="proj-a",
        )
        await resolver.add_triple(live, pool="project")

        # Direct supersede on the in-memory graph store.
        assert resolver._project is not None
        graph = resolver._project.graph
        ok = await graph.supersede_triple(
            subject="operator",
            predicate="prefers",
            object_="minimalist_ui",
            source_passage_id=source_id,
        )
        assert ok is True

        # The superseded triple must still carry its pool's group_id.
        all_triples = await graph.list_triples()
        assert len(all_triples) == 1
        assert all_triples[0].valid_until is not None
        assert all_triples[0].group_id == "p:proj-a"


class TestPhysicalIsolation:
    async def test_two_projects_have_separate_graphs(self, tmp_path: Path) -> None:
        r1 = PoolResolver(project_slug="alpha", home=tmp_path, embedding_dim=8)
        r2 = PoolResolver(project_slug="beta", home=tmp_path, embedding_dim=8)
        await r1.setup()
        await r2.setup()
        try:
            await r1.add_triple(_triple(subject="alpha_only"), pool="project")
            await r2.add_triple(_triple(subject="beta_only"), pool="project")

            alpha_triples = await r1.list_triples(
                pool_scope=PoolScope(project_slug="alpha"),
            )
            beta_triples = await r2.list_triples(
                pool_scope=PoolScope(project_slug="beta"),
            )

            assert {t.subject for t in alpha_triples} == {"alpha_only"}
            assert {t.subject for t in beta_triples} == {"beta_only"}
        finally:
            await r1.teardown()
            await r2.teardown()
