"""CLI router — ADR-006 §4.6 ``select_cli`` over (cli, model) (S6).

Implements the locked three-input algorithm, extended to pick the
**model** inside the CLI (operator 2026-05-24) and resolve its effort:

    1. operator override   (strongest — sticky/single-turn, cli [+ model])
    2. quota filter        (drop ineligible (cli, model); per-model for
                            gemini-cli, per-account for the rest)
    3. RAG affinity argmax (highest dual-pool success-rate over the
                            eligible (cli, model) candidates)

ADR-006 §4.6 locks the input order + deterministic argmax; the affinity
*math* (and now the model dimension) is the open part, scored in Mind
(:class:`~selffork_mind.affinity.CliAffinityResolver`). The chosen CLI's
**effort** comes from the Self-Jr-mutable control config
(:class:`~selffork_orchestrator.router.cli_config.CliRuntimeStore`) — never
hardcoded. Per [[subscription-based-cli]] there is no cost dimension:
quota is a hard eligibility constraint, never folded into the score.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from selffork_mind.affinity import (
    AffinityConfig,
    AffinityScore,
    CliAffinityResolver,
    DuckDBCliAffinityStore,
)
from selffork_mind.affinity.resolver import (
    global_affinity_db_path,
    project_affinity_db_path,
)
from selffork_mind.store.base import GLOBAL_GROUP_ID, project_group_id
from selffork_orchestrator.cli_agent.capabilities import (
    candidate_pairs,
    capability_for,
)
from selffork_orchestrator.heartbeat.filter import (
    DEFAULT_CLI_IDS,
    DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT,
)
from selffork_orchestrator.router.cli_config import CliRuntimeStore
from selffork_orchestrator.router.outcomes import OutcomeIngester, SessionOutcome
from selffork_orchestrator.router.override import CliOverrideStore
from selffork_shared.quota import QuotaSnapshot

__all__ = [
    "CLIRouter",
    "CliAffinityProvider",
    "CliSelection",
    "ModelQuotaReader",
    "QuotaExhaustedAcrossFleetError",
    "SelectionMethod",
]


ModelQuotaReader = Callable[[str, str], Awaitable[QuotaSnapshot | None]]
"""Async ``(cli_id, model) → QuotaSnapshot | None``.

For per-model-quota CLIs (``gemini-cli`` — pro/flash/flash-lite billed
separately, operator 2026-05-24) the model selects the window; for
account-wide CLIs the model is ignored and the account snapshot is
returned. ``None`` ⇒ no signal ⇒ treated as eligible.
"""


SelectionMethod = Literal["override", "affinity", "exploration"]


def _pair_key(cli: str, model: str) -> str:
    return f"{cli}/{model}"


class QuotaExhaustedAcrossFleetError(RuntimeError):
    """Raised when every candidate ``(cli, model)`` is quota-exhausted."""

    def __init__(self, clis: list[str]) -> None:
        self.clis = tuple(clis)
        super().__init__(
            f"all candidate CLIs are quota-exhausted: {sorted(set(clis))}"
        )


@dataclass(frozen=True, slots=True)
class CliSelection:
    """The router's decision for one ``select_cli`` call."""

    cli: str
    model: str
    effort: str | None
    method: SelectionMethod
    reasoning: str
    sticky: bool = False
    scores: dict[str, float] = field(default_factory=dict)
    match_levels: dict[str, str] = field(default_factory=dict)
    eligible: tuple[tuple[str, str], ...] = ()
    quota_filtered: tuple[tuple[str, str], ...] = ()

    def to_metadata(self) -> dict[str, object]:
        """Flatten for :class:`ActionResult` metadata / audit JSONL."""
        return {
            "chosen_cli": self.cli,
            "chosen_model": self.model,
            "effort": self.effort,
            "method": self.method,
            "sticky": self.sticky,
            "scores": dict(self.scores),
            "match_levels": dict(self.match_levels),
            "eligible": [_pair_key(c, m) for c, m in self.eligible],
            "quota_filtered": [_pair_key(c, m) for c, m in self.quota_filtered],
        }


@dataclass
class CliAffinityProvider:
    """Owns affinity DuckDB lifecycle (shared GLOBAL + per-PROJECT cache).

    DuckDB is single-writer per file: the GLOBAL store (written on every
    workspace's outcome) must be one shared handle, while each PROJECT
    pool is its own file with its own cached handle. A
    :class:`CliAffinityResolver` is a cheap view over (project, global)
    handed out per call — it owns no connections.
    """

    home: Path | None = None
    config: AffinityConfig = field(default_factory=AffinityConfig)
    outcome_log_path: Path | None = None
    _global: DuckDBCliAffinityStore | None = field(
        default=None, init=False, repr=False
    )
    _projects: dict[str, DuckDBCliAffinityStore] = field(
        default_factory=dict, init=False, repr=False
    )
    _ingester: OutcomeIngester | None = field(
        default=None, init=False, repr=False
    )

    async def setup(self) -> None:
        """Open the shared GLOBAL store eagerly (fail-fast on DB issues)."""
        await self._ensure_global()

    async def _ensure_global(self) -> DuckDBCliAffinityStore:
        if self._global is None:
            store = DuckDBCliAffinityStore(
                group_id=GLOBAL_GROUP_ID,
                db_path=global_affinity_db_path(home=self.home),
            )
            await store.setup()
            self._global = store
        return self._global

    async def _ensure_project(self, workspace: str) -> DuckDBCliAffinityStore:
        store = self._projects.get(workspace)
        if store is None:
            store = DuckDBCliAffinityStore(
                group_id=project_group_id(workspace),
                db_path=project_affinity_db_path(workspace, home=self.home),
            )
            await store.setup()
            self._projects[workspace] = store
        return store

    async def resolver_for(self, workspace: str | None) -> CliAffinityResolver:
        """A dual-pool resolver bound to ``workspace`` (PROJECT) + GLOBAL."""
        global_store = await self._ensure_global()
        project_store = (
            await self._ensure_project(workspace) if workspace else None
        )
        return CliAffinityResolver(
            project_store=project_store,
            global_store=global_store,
            config=self.config,
        )

    async def record_outcome(
        self,
        *,
        workspace: str | None,
        task_type: str | None,
        cli: str,
        model: str,
        succeeded: bool,
        turns: int,
    ) -> None:
        """Persist one session outcome into both pools."""
        resolver = await self.resolver_for(workspace)
        await resolver.record_outcome(
            task_type=task_type,
            cli=cli,
            model=model,
            succeeded=succeeded,
            turns=turns,
        )

    async def drain(self) -> int:
        """Fold pending subprocess session outcomes into the store.

        Called before every affinity read so the dashboard (the sole DB
        writer) ingests outcomes that ``selffork run`` subprocesses
        appended to the JSONL log. No-op when no log path is configured.
        """
        if self.outcome_log_path is None:
            return 0
        if self._ingester is None:
            self._ingester = OutcomeIngester(log_path=self.outcome_log_path)

        async def _record(outcome: SessionOutcome) -> None:
            await self.record_outcome(
                workspace=outcome.workspace_slug,
                task_type=outcome.task_type,
                cli=outcome.cli,
                model=outcome.model,
                succeeded=outcome.succeeded,
                turns=outcome.turns,
            )

        return await self._ingester.drain(_record)

    async def teardown(self) -> None:
        if self._global is not None:
            await self._global.teardown()
            self._global = None
        for store in self._projects.values():
            await store.teardown()
        self._projects.clear()


@dataclass
class CLIRouter:
    """ADR-006 §4.6 ``select_cli`` — override → quota → affinity argmax,
    over ``(cli, model)`` with control-config-resolved effort."""

    affinity: CliAffinityProvider
    override_store: CliOverrideStore
    runtime_store: CliRuntimeStore
    quota_reader: ModelQuotaReader | None = None
    candidates: tuple[str, ...] = DEFAULT_CLI_IDS
    quota_threshold_pct: float = DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT
    exploration_epsilon: float = 0.0
    rng: random.Random = field(default_factory=random.Random)

    async def select_cli(
        self,
        *,
        workspace: str | None,
        task_type: str | None = None,
        clis: list[str] | None = None,
        consume_override: bool = True,
    ) -> CliSelection:
        """Pick a ``(cli, model)`` + effort. ``consume_override=False``
        previews (one-shots survive). Raises
        :class:`QuotaExhaustedAcrossFleetError` when no candidate passes
        the quota gate."""
        cli_pool = list(clis) if clis is not None else list(self.candidates)

        # 1. operator override (strongest)
        if workspace is not None:
            override = (
                self.override_store.get_active(workspace)
                if consume_override
                else self.override_store.peek(workspace)
            )
            if override is not None and override.cli in cli_pool:
                model = override.model or await self._best_model_for_cli(
                    workspace=workspace, task_type=task_type, cli=override.cli
                )
                kind = "sticky" if override.sticky else "single-turn"
                forced = "cli+model" if override.model else "cli"
                return CliSelection(
                    cli=override.cli,
                    model=model,
                    effort=self.runtime_store.effort_for(override.cli),
                    method="override",
                    sticky=override.sticky,
                    reasoning=(
                        f"operator {kind} override ({forced}) → "
                        f"{override.cli}/{model}"
                    ),
                    eligible=((override.cli, model),),
                )

        # 2. enumerate (cli, model) candidates + quota filter
        pairs = candidate_pairs(
            cli_pool, models_override=self.runtime_store.models_override()
        )
        await self.affinity.drain()
        eligible, filtered = await self._filter_by_quota(pairs)
        if not eligible:
            raise QuotaExhaustedAcrossFleetError([cli for cli, _ in pairs])

        # 3. RAG affinity argmax over eligible (cli, model)
        resolver = await self.affinity.resolver_for(workspace)
        scored = await resolver.score_candidates(
            task_type=task_type, candidates=eligible
        )
        scores_map: dict[str, float] = {
            _pair_key(s.cli, s.model): s.score for s in scored
        }
        levels_map: dict[str, str] = {
            _pair_key(s.cli, s.model): s.match_level for s in scored
        }

        if (
            self.exploration_epsilon > 0.0
            and self.rng.random() < self.exploration_epsilon
        ):
            cli, model = self.rng.choice(eligible)
            method: SelectionMethod = "exploration"
            reasoning = (
                f"exploration (epsilon={self.exploration_epsilon}) → "
                f"{cli}/{model}"
            )
        else:
            best = _argmax(scored)
            cli, model = best.cli, best.model
            method = "affinity"
            reasoning = (
                f"affinity argmax → {cli}/{model} "
                f"(score={best.score:.3f}, level={best.match_level})"
            )
        return CliSelection(
            cli=cli,
            model=model,
            effort=self.runtime_store.effort_for(cli),
            method=method,
            reasoning=reasoning,
            scores=scores_map,
            match_levels=levels_map,
            eligible=tuple(eligible),
            quota_filtered=tuple(filtered),
        )

    async def record_outcome(
        self,
        *,
        workspace: str | None,
        task_type: str | None,
        cli: str,
        model: str,
        succeeded: bool,
        turns: int,
    ) -> None:
        """Feedback path — fold a finished session into the affinity store."""
        await self.affinity.record_outcome(
            workspace=workspace,
            task_type=task_type,
            cli=cli,
            model=model,
            succeeded=succeeded,
            turns=turns,
        )

    async def _best_model_for_cli(
        self, *, workspace: str | None, task_type: str | None, cli: str
    ) -> str:
        """Operator forced a CLI but not a model — affinity-pick the best
        model inside it (falls back to the capability default)."""
        cap = capability_for(cli)
        models = self.runtime_store.enabled_models_for(cli) or (
            cap.models if cap is not None else ()
        )
        if not models:
            return cap.default_model if cap is not None else cli
        resolver = await self.affinity.resolver_for(workspace)
        scored = await resolver.score_candidates(
            task_type=task_type, candidates=[(cli, m) for m in models]
        )
        return _argmax(scored).model

    async def _filter_by_quota(
        self, pairs: list[tuple[str, str]]
    ) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        if self.quota_reader is None:
            return list(pairs), []
        eligible: list[tuple[str, str]] = []
        filtered: list[tuple[str, str]] = []
        for cli, model in pairs:
            snapshot = await self.quota_reader(cli, model)
            if snapshot is not None and snapshot.is_exhausted(
                self.quota_threshold_pct
            ):
                filtered.append((cli, model))
            else:
                eligible.append((cli, model))
        return eligible, filtered


def _argmax(scored: list[AffinityScore]) -> AffinityScore:
    """Deterministic argmax: highest score, then fewer avg turns, then
    candidate order (enumerate index). Total ordering ⇒ stable."""

    def sort_key(item: tuple[int, AffinityScore]) -> tuple[float, float, int]:
        index, score = item
        avg_turns = score.avg_turns if score.avg_turns is not None else float("inf")
        return (-score.score, avg_turns, index)

    return min(enumerate(scored), key=sort_key)[1]
