"""CLI affinity store + resolver tests — ADR-006 §4.6 + ADR-009 (S6).

Covers the scoring math (Laplace + shrink), both storage backends
(InMemory + DuckDB, incl. persistence + None-task sentinel + the
``(task, cli, model)`` key), and the dual-pool resolver backoff
(project_leaf → global_task → global_cli_model → global_cli → prior) on
real DuckDB engines via tmp_path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from selffork_mind.affinity import (
    AffinityConfig,
    CliAffinityResolver,
    DuckDBCliAffinityStore,
    InMemoryCliAffinityStore,
    build_duckdb_affinity_resolver,
    laplace_rate,
    shrink,
)
from selffork_mind.affinity.resolver import (
    global_affinity_db_path,
    project_affinity_db_path,
)
from selffork_mind.store.base import GLOBAL_GROUP_ID, project_group_id

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


_CFG = AffinityConfig()
_AT = datetime(2026, 5, 24, tzinfo=UTC)


# ── scoring math ──────────────────────────────────────────────────────


class TestScoringMath:
    def test_laplace_cold_start_is_half(self) -> None:
        assert laplace_rate(0.0, 0.0, _CFG) == pytest.approx(0.5)

    def test_laplace_pure_success(self) -> None:
        assert laplace_rate(3.0, 0.0, _CFG) == pytest.approx(0.8)

    def test_laplace_pure_failure(self) -> None:
        assert laplace_rate(0.0, 3.0, _CFG) == pytest.approx(0.2)

    def test_laplace_converges_with_evidence(self) -> None:
        assert laplace_rate(100.0, 0.0, _CFG) > laplace_rate(1.0, 0.0, _CFG)
        assert laplace_rate(100.0, 0.0, _CFG) < 1.0

    def test_shrink_empty_leaf_defers_to_parent(self) -> None:
        assert shrink(0.9, 0.0, 0.5, _CFG) == pytest.approx(0.5)

    def test_shrink_weights_by_observations(self) -> None:
        assert shrink(0.8, 4.0, 0.5, _CFG) == pytest.approx(0.65)

    def test_shrink_trusts_dense_leaf(self) -> None:
        assert shrink(0.8, 1000.0, 0.5, _CFG) == pytest.approx(0.8, abs=0.01)

    def test_shrink_k_zero(self) -> None:
        cfg = AffinityConfig(shrinkage_k=0.0)
        assert shrink(0.8, 1.0, 0.5, cfg) == pytest.approx(0.8)
        assert shrink(0.8, 0.0, 0.5, cfg) == pytest.approx(0.5)


class TestAffinityConfig:
    def test_defaults_valid(self) -> None:
        assert AffinityConfig().decay_gamma == 0.97

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"alpha": 0.0},
            {"beta": -1.0},
            {"decay_gamma": 0.0},
            {"decay_gamma": 1.5},
            {"shrinkage_k": -0.1},
        ],
    )
    def test_invalid_params_raise(self, kwargs: dict[str, float]) -> None:
        with pytest.raises(ValueError):
            AffinityConfig(**kwargs)


# ── InMemory store ────────────────────────────────────────────────────


class TestInMemoryStore:
    async def test_record_creates_observation(self) -> None:
        store = InMemoryCliAffinityStore(group_id="p:demo")
        rec = await store.record(
            task_type="refactor",
            cli="claude-code",
            model="opus",
            succeeded=True,
            turns=5,
            decay_gamma=0.97,
            now=_AT,
        )
        assert rec.success == pytest.approx(1.0)
        assert rec.observations == pytest.approx(1.0)
        assert rec.avg_turns == pytest.approx(5.0)
        assert rec.model == "opus"

    async def test_record_decays(self) -> None:
        store = InMemoryCliAffinityStore(group_id="p:demo")
        await store.record(
            task_type="t",
            cli="c",
            model="m",
            succeeded=True,
            turns=2,
            decay_gamma=0.5,
        )
        rec = await store.record(
            task_type="t",
            cli="c",
            model="m",
            succeeded=False,
            turns=4,
            decay_gamma=0.5,
        )
        assert rec.success == pytest.approx(0.5)
        assert rec.failure == pytest.approx(1.0)
        assert rec.observations == pytest.approx(1.5)

    async def test_get_missing_returns_none(self) -> None:
        store = InMemoryCliAffinityStore(group_id="g:global")
        assert await store.get(task_type="t", cli="c", model="m") is None

    async def test_model_isolation(self) -> None:
        store = InMemoryCliAffinityStore(group_id="p:demo")
        await store.record(
            task_type="t",
            cli="c",
            model="m1",
            succeeded=True,
            turns=1,
            decay_gamma=1.0,
        )
        await store.record(
            task_type="t",
            cli="c",
            model="m2",
            succeeded=False,
            turns=1,
            decay_gamma=1.0,
        )
        m1 = await store.get(task_type="t", cli="c", model="m1")
        m2 = await store.get(task_type="t", cli="c", model="m2")
        assert m1 is not None and m1.success == pytest.approx(1.0)
        assert m2 is not None and m2.failure == pytest.approx(1.0)

    async def test_aggregate_cli_model_sums_tasks(self) -> None:
        store = InMemoryCliAffinityStore(group_id="g:global")
        await store.record(
            task_type="a",
            cli="c",
            model="m1",
            succeeded=True,
            turns=1,
            decay_gamma=1.0,
        )
        await store.record(
            task_type="b",
            cli="c",
            model="m1",
            succeeded=True,
            turns=3,
            decay_gamma=1.0,
        )
        cm = await store.aggregate_cli_model(cli="c", model="m1")
        assert cm is not None
        assert cm.observations == pytest.approx(2.0)
        assert cm.success == pytest.approx(2.0)
        assert cm.model == "m1"
        assert cm.task_type is None

    async def test_aggregate_cli_sums_across_models(self) -> None:
        store = InMemoryCliAffinityStore(group_id="g:global")
        await store.record(
            task_type="a",
            cli="c",
            model="m1",
            succeeded=True,
            turns=1,
            decay_gamma=1.0,
        )
        await store.record(
            task_type="a",
            cli="c",
            model="m2",
            succeeded=True,
            turns=1,
            decay_gamma=1.0,
        )
        agg = await store.aggregate_cli(cli="c")
        assert agg is not None
        assert agg.observations == pytest.approx(2.0)
        assert agg.model is None  # model-agnostic aggregate

    async def test_aggregate_unseen_returns_none(self) -> None:
        store = InMemoryCliAffinityStore(group_id="g:global")
        assert await store.aggregate_cli(cli="never") is None
        assert await store.aggregate_cli_model(cli="never", model="m") is None

    async def test_none_task_roundtrips(self) -> None:
        store = InMemoryCliAffinityStore(group_id="p:demo")
        await store.record(
            task_type=None,
            cli="c",
            model="m",
            succeeded=True,
            turns=1,
            decay_gamma=1.0,
        )
        cell = await store.get(task_type=None, cli="c", model="m")
        assert cell is not None and cell.task_type is None


# ── DuckDB store ──────────────────────────────────────────────────────


class TestDuckDBStore:
    async def test_require_open_before_setup(self, tmp_path: Path) -> None:
        store = DuckDBCliAffinityStore(group_id="p:demo", db_path=tmp_path / "a.duckdb")
        with pytest.raises(RuntimeError, match="not open"):
            await store.get(task_type="t", cli="c", model="m")

    async def test_record_get_aggregates(self, tmp_path: Path) -> None:
        store = DuckDBCliAffinityStore(group_id="g:global", db_path=tmp_path / "aff.duckdb")
        await store.setup()
        try:
            await store.record(
                task_type="a",
                cli="codex",
                model="gpt-5.5",
                succeeded=True,
                turns=2,
                decay_gamma=1.0,
            )
            await store.record(
                task_type="b",
                cli="codex",
                model="gpt-5.4",
                succeeded=False,
                turns=6,
                decay_gamma=1.0,
            )
            cell = await store.get(task_type="a", cli="codex", model="gpt-5.5")
            assert cell is not None
            assert cell.success == pytest.approx(1.0)
            assert cell.avg_turns == pytest.approx(2.0)
            cm = await store.aggregate_cli_model(cli="codex", model="gpt-5.5")
            assert cm is not None and cm.observations == pytest.approx(1.0)
            cli_agg = await store.aggregate_cli(cli="codex")
            assert cli_agg is not None
            assert cli_agg.observations == pytest.approx(2.0)
            assert cli_agg.success == pytest.approx(1.0)
        finally:
            await store.teardown()

    async def test_none_task_sentinel(self, tmp_path: Path) -> None:
        store = DuckDBCliAffinityStore(group_id="p:demo", db_path=tmp_path / "aff.duckdb")
        await store.setup()
        try:
            await store.record(
                task_type=None,
                cli="c",
                model="m",
                succeeded=True,
                turns=1,
                decay_gamma=1.0,
            )
            cell = await store.get(task_type=None, cli="c", model="m")
            assert cell is not None and cell.task_type is None
        finally:
            await store.teardown()

    async def test_persistence_across_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "aff.duckdb"
        first = DuckDBCliAffinityStore(group_id="p:demo", db_path=db)
        await first.setup()
        await first.record(
            task_type="t",
            cli="c",
            model="m",
            succeeded=True,
            turns=3,
            decay_gamma=1.0,
        )
        await first.teardown()

        second = DuckDBCliAffinityStore(group_id="p:demo", db_path=db)
        await second.setup()
        try:
            cell = await second.get(task_type="t", cli="c", model="m")
            assert cell is not None and cell.success == pytest.approx(1.0)
            assert len(await second.list_records()) == 1
        finally:
            await second.teardown()


# ── Resolver (dual-pool backoff with model) ───────────────────────────


def _resolver(
    *, with_project: bool = True, config: AffinityConfig | None = None
) -> CliAffinityResolver:
    project = InMemoryCliAffinityStore(group_id="p:demo") if with_project else None
    return CliAffinityResolver(
        project_store=project,
        global_store=InMemoryCliAffinityStore(group_id="g:global"),
        config=config or AffinityConfig(),
    )


class TestResolver:
    async def test_cold_start_scores_prior(self) -> None:
        res = _resolver()
        score = await res.score(task_type="refactor", cli="claude-code", model="opus")
        assert score.score == pytest.approx(0.5)
        assert score.match_level == "prior"
        assert score.model == "opus"

    async def test_record_outcome_writes_both_pools(self) -> None:
        res = _resolver()
        await res.record_outcome(
            task_type="t", cli="codex", model="gpt-5.5", succeeded=True, turns=2
        )
        assert res.project_store is not None
        proj = await res.project_store.get(task_type="t", cli="codex", model="gpt-5.5")
        glob = await res.global_store.get(task_type="t", cli="codex", model="gpt-5.5")
        assert proj is not None and proj.success == pytest.approx(1.0)
        assert glob is not None and glob.success == pytest.approx(1.0)

    async def test_project_leaf_dominates(self) -> None:
        res = _resolver()
        for _ in range(12):
            await res.record_outcome(
                task_type="refactor",
                cli="claude-code",
                model="opus",
                succeeded=True,
                turns=4,
            )
        score = await res.score(task_type="refactor", cli="claude-code", model="opus")
        assert score.match_level == "project_leaf"
        assert score.score > 0.7
        assert score.avg_turns == pytest.approx(4.0, abs=0.01)

    async def test_global_task_fallback(self) -> None:
        res = _resolver(with_project=False)
        for _ in range(6):
            await res.record_outcome(
                task_type="test",
                cli="codex",
                model="gpt-5.5",
                succeeded=True,
                turns=3,
            )
        score = await res.score(task_type="test", cli="codex", model="gpt-5.5")
        assert score.match_level == "global_task"
        assert score.score > 0.5

    async def test_global_cli_model_fallback_unseen_task(self) -> None:
        res = _resolver(with_project=False)
        for _ in range(8):
            await res.record_outcome(
                task_type="refactor",
                cli="codex",
                model="gpt-5.5",
                succeeded=True,
                turns=2,
            )
        # unseen task, but the (cli, model) pair has history
        score = await res.score(task_type="brand-new-task", cli="codex", model="gpt-5.5")
        assert score.match_level == "global_cli_model"
        assert score.score > 0.5

    async def test_global_cli_prior_lifts_new_model(self) -> None:
        res = _resolver(with_project=False)
        for _ in range(8):
            await res.record_outcome(
                task_type="t",
                cli="codex",
                model="gpt-5.5",
                succeeded=True,
                turns=2,
            )
        # a brand-new model under the known-good codex CLI inherits its prior
        score = await res.score(task_type="t", cli="codex", model="gpt-9-unreleased")
        assert score.match_level == "global_cli"
        assert score.score > 0.5

    async def test_success_model_outscores_failure_model(self) -> None:
        res = _resolver()
        for _ in range(8):
            await res.record_outcome(
                task_type="t",
                cli="codex",
                model="winner",
                succeeded=True,
                turns=2,
            )
            await res.record_outcome(
                task_type="t",
                cli="codex",
                model="loser",
                succeeded=False,
                turns=9,
            )
        scores = await res.score_candidates(
            task_type="t", candidates=[("codex", "winner"), ("codex", "loser")]
        )
        by_model = {s.model: s for s in scores}
        assert by_model["winner"].score > by_model["loser"].score
        best = max(scores, key=lambda s: s.score)
        assert (best.cli, best.model) == ("codex", "winner")

    async def test_score_candidates_covers_pairs(self) -> None:
        res = _resolver()
        scores = await res.score_candidates(
            task_type="t",
            candidates=[("codex", "gpt-5.5"), ("claude-code", "opus")],
        )
        assert {(s.cli, s.model) for s in scores} == {
            ("codex", "gpt-5.5"),
            ("claude-code", "opus"),
        }
        assert all(0.0 <= s.score <= 1.0 for s in scores)


# ── DuckDB factory integration ────────────────────────────────────────


class TestFactory:
    def test_db_paths_follow_adr009_layout(self, tmp_path: Path) -> None:
        proj = project_affinity_db_path("foo", home=tmp_path)
        glob = global_affinity_db_path(home=tmp_path)
        assert proj == tmp_path / "projects" / "foo" / "mind" / "cli_affinity.duckdb"
        assert glob == tmp_path / "global" / "mind" / "cli_affinity.duckdb"

    async def test_build_record_score_roundtrip(self, tmp_path: Path) -> None:
        res = build_duckdb_affinity_resolver(project_slug="demo", home=tmp_path)
        await res.setup()
        try:
            assert res.project_store is not None
            assert res.project_store.group_id == project_group_id("demo")
            assert res.global_store.group_id == GLOBAL_GROUP_ID
            for _ in range(5):
                await res.record_outcome(
                    task_type="build",
                    cli="claude-code",
                    model="opus",
                    succeeded=True,
                    turns=3,
                )
            score = await res.score(task_type="build", cli="claude-code", model="opus")
            assert score.match_level == "project_leaf"
            assert score.score > 0.6
        finally:
            await res.teardown()

    async def test_global_only_resolver(self, tmp_path: Path) -> None:
        res = build_duckdb_affinity_resolver(project_slug=None, home=tmp_path)
        await res.setup()
        try:
            assert res.project_store is None
            score = await res.score(task_type="t", cli="codex", model="m")
            assert score.match_level == "prior"
        finally:
            await res.teardown()
