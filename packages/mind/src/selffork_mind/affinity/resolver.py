"""Dual-pool CLI affinity resolver — ADR-006 §4.6 + ADR-009 (S6).

Coordinates a PROJECT store (codebase-specific affinity leaf) and the
shared GLOBAL store (operator cross-project reflex) into one
hierarchical score per ``(cli, model)`` candidate. The resolver owns no
connections — the orchestrator router builds/caches the stores and their
lifecycle; the resolver is a cheap, injectable coordinator (so tests pass
two :class:`InMemoryCliAffinityStore` instances).

Scoring backoff (sparse PROJECT leaf → GLOBAL parents → ``0.5`` prior),
per :mod:`selffork_mind.affinity.model`:

    PROJECT (ws, task, cli, model)
      └─shrink→ GLOBAL (task, cli, model)
          └─shrink→ GLOBAL (cli, model)        [all tasks]
              └─shrink→ GLOBAL (cli)           [all models — CLI prior]
                  └─shrink→ 0.5
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from selffork_mind.affinity.model import (
    AffinityConfig,
    AffinityRecord,
    AffinityScore,
    MatchLevel,
    laplace_rate,
    shrink,
)
from selffork_mind.affinity.store import (
    CliAffinityStore,
    DuckDBCliAffinityStore,
)
from selffork_mind.store.base import GLOBAL_GROUP_ID, project_group_id
from selffork_mind.store.pool import (
    default_global_pool_root,
    default_project_pool_root,
)

__all__ = [
    "CliAffinityResolver",
    "build_duckdb_affinity_resolver",
    "global_affinity_db_path",
    "project_affinity_db_path",
]


def project_affinity_db_path(project_slug: str, *, home: Path | None = None) -> Path:
    """``~/.selffork/projects/<slug>/mind/cli_affinity.duckdb``."""
    return default_project_pool_root(project_slug, home=home) / "cli_affinity.duckdb"


def global_affinity_db_path(*, home: Path | None = None) -> Path:
    """``~/.selffork/global/mind/cli_affinity.duckdb``."""
    return default_global_pool_root(home=home) / "cli_affinity.duckdb"


def _rate_and_obs(record: AffinityRecord | None, config: AffinityConfig) -> tuple[float, float]:
    """``(laplace_rate, observations)`` for a level, or ``(0.5, 0)``.

    An empty level contributes ``observations == 0`` so :func:`shrink`
    gives it zero weight — the prior placeholder rate is never trusted.
    """
    if record is None or record.observations <= 0.0:
        return 0.5, 0.0
    return laplace_rate(record.success, record.failure, config), record.observations


def _deepest_level(
    project_leaf: AffinityRecord | None,
    global_task: AffinityRecord | None,
    global_cli_model: AffinityRecord | None,
    global_cli: AffinityRecord | None,
) -> tuple[MatchLevel, float | None]:
    """Deepest backoff level carrying data → ``(level, avg_turns)``."""
    if project_leaf is not None and project_leaf.observations > 0.0:
        return "project_leaf", project_leaf.avg_turns
    if global_task is not None and global_task.observations > 0.0:
        return "global_task", global_task.avg_turns
    if global_cli_model is not None and global_cli_model.observations > 0.0:
        return "global_cli_model", global_cli_model.avg_turns
    if global_cli is not None and global_cli.observations > 0.0:
        return "global_cli", global_cli.avg_turns
    return "prior", None


@dataclass
class CliAffinityResolver:
    """Dual-pool affinity coordinator (ADR-009 PROJECT + GLOBAL).

    Construct with the workspace's PROJECT store (``None`` when there is
    no active workspace — scoring then starts at the GLOBAL level) and
    the shared GLOBAL store. The orchestrator router owns store
    lifecycle; :meth:`setup`/:meth:`teardown` here are convenience
    pass-throughs for standalone use (tests, ``selffork mind`` CLI).
    """

    project_store: CliAffinityStore | None
    global_store: CliAffinityStore
    config: AffinityConfig = field(default_factory=AffinityConfig)

    async def setup(self) -> None:
        if self.project_store is not None:
            await self.project_store.setup()
        await self.global_store.setup()

    async def teardown(self) -> None:
        if self.project_store is not None:
            await self.project_store.teardown()
        await self.global_store.teardown()

    async def record_outcome(
        self,
        *,
        task_type: str | None,
        cli: str,
        model: str,
        succeeded: bool,
        turns: int,
        now: datetime | None = None,
    ) -> None:
        """Fold one session outcome into both pools.

        The PROJECT leaf captures this workspace's ``(task, cli, model)``
        affinity; the GLOBAL pool accumulates the same outcome as
        cross-project operator reflex (and serves as the backoff prior
        for sparse leaves and brand-new models).
        """
        gamma = self.config.decay_gamma
        if self.project_store is not None:
            await self.project_store.record(
                task_type=task_type,
                cli=cli,
                model=model,
                succeeded=succeeded,
                turns=turns,
                decay_gamma=gamma,
                now=now,
            )
        await self.global_store.record(
            task_type=task_type,
            cli=cli,
            model=model,
            succeeded=succeeded,
            turns=turns,
            decay_gamma=gamma,
            now=now,
        )

    async def score(self, *, task_type: str | None, cli: str, model: str) -> AffinityScore:
        """Hierarchical, smoothed success-rate for one ``(cli, model)``."""
        cfg = self.config
        # Level 4 (coarsest): GLOBAL aggregate over all models for cli.
        global_cli = await self.global_store.aggregate_cli(cli=cli)
        rate_c, obs_c = _rate_and_obs(global_cli, cfg)
        score_cli = shrink(rate_c, obs_c, 0.5, cfg)
        # Level 3: GLOBAL aggregate over all tasks for (cli, model).
        global_cli_model = await self.global_store.aggregate_cli_model(cli=cli, model=model)
        rate_cm, obs_cm = _rate_and_obs(global_cli_model, cfg)
        score_cli_model = shrink(rate_cm, obs_cm, score_cli, cfg)
        # Level 2: GLOBAL (task, cli, model).
        global_task = await self.global_store.get(task_type=task_type, cli=cli, model=model)
        rate_t, obs_t = _rate_and_obs(global_task, cfg)
        score_task = shrink(rate_t, obs_t, score_cli_model, cfg)
        # Level 1 (leaf): PROJECT (task, cli, model).
        project_leaf = (
            await self.project_store.get(task_type=task_type, cli=cli, model=model)
            if self.project_store is not None
            else None
        )
        rate_l, obs_l = _rate_and_obs(project_leaf, cfg)
        final = shrink(rate_l, obs_l, score_task, cfg)
        match_level, avg_turns = _deepest_level(
            project_leaf, global_task, global_cli_model, global_cli
        )
        return AffinityScore(
            cli=cli,
            model=model,
            score=final,
            match_level=match_level,
            observations=obs_l,
            avg_turns=avg_turns,
        )

    async def score_candidates(
        self, *, task_type: str | None, candidates: list[tuple[str, str]]
    ) -> list[AffinityScore]:
        """Score every ``(cli, model)`` candidate (router argmax input)."""
        return [
            await self.score(task_type=task_type, cli=cli, model=model) for cli, model in candidates
        ]


def build_duckdb_affinity_resolver(
    *,
    project_slug: str | None,
    home: Path | None = None,
    config: AffinityConfig | None = None,
) -> CliAffinityResolver:
    """Construct a file-backed dual-pool resolver (call ``setup()`` next).

    PROJECT store is omitted when ``project_slug`` is ``None`` (global-
    only scoring). Both pools live under the ADR-009 §2 directory layout.
    """
    project_store: CliAffinityStore | None = None
    if project_slug:
        project_store = DuckDBCliAffinityStore(
            group_id=project_group_id(project_slug),
            db_path=project_affinity_db_path(project_slug, home=home),
        )
    global_store = DuckDBCliAffinityStore(
        group_id=GLOBAL_GROUP_ID,
        db_path=global_affinity_db_path(home=home),
    )
    return CliAffinityResolver(
        project_store=project_store,
        global_store=global_store,
        config=config or AffinityConfig(),
    )
