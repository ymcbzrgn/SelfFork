"""CLIRouter tests — ADR-006 §4.6 over (cli, model) + effort + quota (S6).

Real DuckDB affinity + YAML override/runtime stores on tmp_path (no-mock)
plus injected fake (cli, model) quota readers. One asyncio loop per test.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from selffork_orchestrator.dashboard.settings.store import YamlSettingsStore
from selffork_orchestrator.router import (
    CliAffinityProvider,
    CliOverrideStore,
    CLIRouter,
    CliRuntimeConfig,
    CliRuntimeStore,
    QuotaExhaustedAcrossFleetError,
    StickyOverrides,
)
from selffork_orchestrator.router.affinity import ModelQuotaReader
from selffork_shared.quota import QuotaSnapshot, WindowKind, WindowState

pytestmark = pytest.mark.asyncio


def _quota(cli_id: str, used_pct: float) -> QuotaSnapshot:
    now = datetime.now(UTC)
    return QuotaSnapshot(
        cli_id=cli_id,
        source="test",
        captured_at=now,
        windows={
            WindowKind.five_hour: WindowState(
                used_pct=used_pct,
                resets_at=now + timedelta(hours=5),
                window_seconds=18000,
            ),
        },
    )


def _reader(exhausted: set[tuple[str, str]]) -> ModelQuotaReader:
    async def reader(cli: str, model: str) -> QuotaSnapshot | None:
        return _quota(cli, 99.0 if (cli, model) in exhausted else 10.0)

    return reader


def _router(
    tmp_path: Path,
    *,
    quota_reader: ModelQuotaReader | None = None,
    candidates: tuple[str, ...] = ("claude-code", "codex", "opencode"),
    epsilon: float = 0.0,
    rng: random.Random | None = None,
) -> CLIRouter:
    override = CliOverrideStore(
        sticky_store=YamlSettingsStore(
            path=tmp_path / "override.yaml",
            schema=StickyOverrides,
            default_factory=StickyOverrides,
        )
    )
    runtime = CliRuntimeStore(
        store=YamlSettingsStore(
            path=tmp_path / "runtime.yaml",
            schema=CliRuntimeConfig,
            default_factory=CliRuntimeConfig,
        )
    )
    return CLIRouter(
        affinity=CliAffinityProvider(home=tmp_path),
        override_store=override,
        runtime_store=runtime,
        quota_reader=quota_reader,
        candidates=candidates,
        exploration_epsilon=epsilon,
        rng=rng or random.Random(),  # noqa: S311 — exploration RNG, non-crypto
    )


async def test_sticky_override_cli_and_model(tmp_path: Path) -> None:
    router = _router(tmp_path)
    router.override_store.set(workspace="demo", cli="codex", model="gpt-5.3-codex", sticky=True)
    sel = await router.select_cli(workspace="demo", task_type="t")
    assert sel.method == "override"
    assert sel.cli == "codex"
    assert sel.model == "gpt-5.3-codex"
    assert sel.effort == "xhigh"  # codex capability seed default


async def test_override_cli_only_affinity_picks_model(tmp_path: Path) -> None:
    router = _router(tmp_path)
    router.override_store.set(workspace="demo", cli="codex", sticky=True)
    sel = await router.select_cli(workspace="demo", task_type="t")
    assert sel.method == "override"
    assert sel.cli == "codex"
    # cold-start ⇒ tie-break to first capability model
    assert sel.model == "gpt-5.5"


async def test_single_turn_override_then_affinity(tmp_path: Path) -> None:
    router = _router(tmp_path)
    router.override_store.set(workspace="demo", cli="opencode", sticky=False)
    first = await router.select_cli(workspace="demo")
    assert first.method == "override"
    assert first.cli == "opencode"
    second = await router.select_cli(workspace="demo")
    assert second.method == "affinity"


async def test_override_unknown_cli_ignored(tmp_path: Path) -> None:
    router = _router(tmp_path, candidates=("claude-code", "codex"))
    router.override_store.set(workspace="demo", cli="opencode", sticky=True)
    sel = await router.select_cli(workspace="demo")
    assert sel.method == "affinity"
    assert sel.cli in {"claude-code", "codex"}


async def test_effort_resolved_from_capability_seed(tmp_path: Path) -> None:
    router = _router(tmp_path, candidates=("claude-code",))
    sel = await router.select_cli(workspace="demo", task_type="t")
    assert sel.cli == "claude-code"
    assert sel.effort == "max"  # operator always-max seed default


async def test_effort_resolved_from_runtime_override(tmp_path: Path) -> None:
    router = _router(tmp_path, candidates=("claude-code",))
    router.runtime_store.set_effort(cli="claude-code", effort="low")
    sel = await router.select_cli(workspace="demo", task_type="t")
    assert sel.effort == "low"


async def test_per_model_quota_filters_one_gemini_model(
    tmp_path: Path,
) -> None:
    # gemini pro exhausted, flash + flash-lite fine (operator: gemini
    # per-model quota). The router filters only the exhausted pair.
    router = _router(
        tmp_path,
        candidates=("gemini-cli",),
        quota_reader=_reader({("gemini-cli", "gemini-2.5-pro")}),
    )
    sel = await router.select_cli(workspace="demo", task_type="t")
    assert ("gemini-cli", "gemini-2.5-pro") in sel.quota_filtered
    assert sel.model != "gemini-2.5-pro"
    assert ("gemini-cli", "gemini-2.5-pro") not in sel.eligible


async def test_all_exhausted_raises(tmp_path: Path) -> None:
    # exhaust every (codex, model) pair
    from selffork_orchestrator.cli_agent.capabilities import capability_for

    cap = capability_for("codex")
    assert cap is not None
    router = _router(
        tmp_path,
        candidates=("codex",),
        quota_reader=_reader({("codex", m) for m in cap.models}),
    )
    with pytest.raises(QuotaExhaustedAcrossFleetError):
        await router.select_cli(workspace="demo")


async def test_affinity_argmax_picks_winning_model(tmp_path: Path) -> None:
    router = _router(tmp_path, candidates=("codex",))
    router.runtime_store.set_enabled_models(cli="codex", models=["gpt-5.5", "gpt-5.4"])
    for _ in range(8):
        await router.affinity.record_outcome(
            workspace="demo",
            task_type="t",
            cli="codex",
            model="gpt-5.5",
            succeeded=True,
            turns=2,
        )
        await router.affinity.record_outcome(
            workspace="demo",
            task_type="t",
            cli="codex",
            model="gpt-5.4",
            succeeded=False,
            turns=9,
        )
    sel = await router.select_cli(workspace="demo", task_type="t")
    assert sel.method == "affinity"
    assert sel.cli == "codex"
    assert sel.model == "gpt-5.5"
    assert sel.scores["codex/gpt-5.5"] > sel.scores["codex/gpt-5.4"]


async def test_exploration_epsilon_one(tmp_path: Path) -> None:
    router = _router(
        tmp_path,
        candidates=("codex",),
        epsilon=1.0,
        rng=random.Random(7),  # noqa: S311
    )
    sel = await router.select_cli(workspace="demo", task_type="t")
    assert sel.method == "exploration"
    assert (sel.cli, sel.model) in sel.eligible


async def test_record_outcome_roundtrip(tmp_path: Path) -> None:
    router = _router(tmp_path)
    await router.record_outcome(
        workspace="demo",
        task_type="t",
        cli="codex",
        model="gpt-5.5",
        succeeded=True,
        turns=3,
    )
    resolver = await router.affinity.resolver_for("demo")
    score = await resolver.score(task_type="t", cli="codex", model="gpt-5.5")
    assert score.match_level == "project_leaf"
    assert score.score > 0.5


async def test_selection_metadata_shape(tmp_path: Path) -> None:
    router = _router(tmp_path, candidates=("codex",))
    sel = await router.select_cli(workspace="demo", task_type="t")
    meta = sel.to_metadata()
    assert meta["chosen_cli"] == sel.cli
    assert meta["chosen_model"] == sel.model
    assert "effort" in meta
    assert set(meta) >= {
        "chosen_cli",
        "chosen_model",
        "effort",
        "method",
        "scores",
        "eligible",
    }
