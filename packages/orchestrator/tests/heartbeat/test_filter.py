"""S-Auto Faz B — LegalActionFilter + WorldStateBuilder tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from selffork_orchestrator.heartbeat.actions import LegalAction
from selffork_orchestrator.heartbeat.config import HeartbeatConfig
from selffork_orchestrator.heartbeat.filter import (
    DEFAULT_CLI_IDS,
    DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT,
    LegalActionFilter,
    WorldState,
    WorldStateBuilder,
)
from selffork_orchestrator.telegram.inbound_router import PauseSignal
from selffork_shared.quota import QuotaSnapshot, WindowKind, WindowState

# ── Fixtures ────────────────────────────────────────────────────────


def _snap(*, cli_id: str, used_pct: float = 25.0) -> QuotaSnapshot:
    now = datetime.now(UTC)
    return QuotaSnapshot(
        cli_id=cli_id,
        windows={
            WindowKind.five_hour: WindowState(
                used_pct=used_pct,
                resets_at=now + timedelta(hours=5),
                window_seconds=18000,
            ),
        },
        captured_at=now,
        source="test",
    )


def _healthy_state(**overrides: object) -> WorldState:
    base: dict[str, object] = dict(
        pause_active=False,
        within_active_hours=True,
        active_concurrent_sessions=0,
        max_concurrent_sessions=1,
        creative_mode_enabled=True,
        cli_quota={cli: _snap(cli_id=cli) for cli in DEFAULT_CLI_IDS},
        quota_exhaustion_threshold_pct=DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT,
        supervised_mode=False,
        last_active_workspace="alpha",
    )
    base.update(overrides)
    return WorldState(**base)  # type: ignore[arg-type]


# ── LegalAction enum ────────────────────────────────────────────────


def test_legal_action_enum_count_matches_adr() -> None:
    """ADR-008 §4.4 declares exactly 8 actions; the enum must match."""
    assert len({*LegalAction}) == 8


def test_legal_action_values_are_turkish_labels() -> None:
    assert LegalAction.TASK_START.value == "task_başlat"
    assert LegalAction.WAIT.value == "bekle"
    assert LegalAction.SELF_STOP.value == "kendini_durdur"


# ── WorldState helpers ──────────────────────────────────────────────


def test_world_state_cli_has_quota_treats_missing_as_healthy() -> None:
    state = _healthy_state(cli_quota={"claude-code": None})
    assert state.cli_has_quota("claude-code") is True


def test_world_state_cli_has_quota_respects_threshold() -> None:
    state = _healthy_state(
        cli_quota={"claude-code": _snap(cli_id="claude-code", used_pct=99.0)},
        quota_exhaustion_threshold_pct=90.0,
    )
    assert state.cli_has_quota("claude-code") is False


def test_world_state_any_cli_has_quota_empty_dict() -> None:
    """Empty cli_quota ⇒ no gate (no signal ⇒ permissive)."""
    state = _healthy_state(cli_quota={})
    assert state.any_cli_has_quota() is True


def test_world_state_any_cli_has_quota_all_exhausted() -> None:
    state = _healthy_state(
        cli_quota={cli: _snap(cli_id=cli, used_pct=99.0) for cli in DEFAULT_CLI_IDS},
    )
    assert state.any_cli_has_quota() is False


def test_world_state_any_cli_has_quota_one_healthy() -> None:
    quotas = {cli: _snap(cli_id=cli, used_pct=99.0) for cli in DEFAULT_CLI_IDS}
    quotas["gemini-cli"] = _snap(cli_id="gemini-cli", used_pct=10.0)
    state = _healthy_state(cli_quota=quotas)
    assert state.any_cli_has_quota() is True


# ── LegalActionFilter rules ─────────────────────────────────────────


def test_filter_full_set_when_healthy() -> None:
    legal = LegalActionFilter().legal_actions(_healthy_state())
    assert legal == frozenset(LegalAction)


def test_filter_pause_short_circuits() -> None:
    legal = LegalActionFilter().legal_actions(_healthy_state(pause_active=True))
    assert legal == frozenset({LegalAction.WAIT, LegalAction.SELF_STOP})


def test_filter_pause_overrides_quota_and_concurrency() -> None:
    state = _healthy_state(
        pause_active=True,
        active_concurrent_sessions=10,
        cli_quota={cli: _snap(cli_id=cli, used_pct=99.0) for cli in DEFAULT_CLI_IDS},
    )
    legal = LegalActionFilter().legal_actions(state)
    assert legal == frozenset({LegalAction.WAIT, LegalAction.SELF_STOP})


def test_filter_outside_active_hours_only_wait() -> None:
    legal = LegalActionFilter().legal_actions(
        _healthy_state(within_active_hours=False)
    )
    assert legal == frozenset({LegalAction.WAIT})


def test_filter_pause_beats_outside_active_hours() -> None:
    """Pause is a stricter gate than active-hours; SELF_STOP must remain."""
    legal = LegalActionFilter().legal_actions(
        _healthy_state(pause_active=True, within_active_hours=False)
    )
    assert LegalAction.SELF_STOP in legal


def test_filter_concurrency_full_drops_task_start() -> None:
    legal = LegalActionFilter().legal_actions(
        _healthy_state(active_concurrent_sessions=1, max_concurrent_sessions=1)
    )
    assert LegalAction.TASK_START not in legal
    assert LegalAction.SESSION_RESUME in legal


def test_filter_concurrency_below_keeps_task_start() -> None:
    legal = LegalActionFilter().legal_actions(
        _healthy_state(active_concurrent_sessions=0, max_concurrent_sessions=2)
    )
    assert LegalAction.TASK_START in legal


def test_filter_all_exhausted_drops_task_start_and_cli_select() -> None:
    state = _healthy_state(
        cli_quota={cli: _snap(cli_id=cli, used_pct=99.0) for cli in DEFAULT_CLI_IDS},
    )
    legal = LegalActionFilter().legal_actions(state)
    assert LegalAction.TASK_START not in legal
    assert LegalAction.CLI_SELECT not in legal
    # Other actions still legal — operator can still be asked, idea
    # mode can run, kanban can be suggested, daemon can wait.
    assert LegalAction.OPERATOR_ASK in legal


def test_filter_one_cli_healthy_keeps_task_start() -> None:
    quotas = {cli: _snap(cli_id=cli, used_pct=99.0) for cli in DEFAULT_CLI_IDS}
    quotas["codex"] = _snap(cli_id="codex", used_pct=10.0)
    legal = LegalActionFilter().legal_actions(_healthy_state(cli_quota=quotas))
    assert LegalAction.TASK_START in legal
    assert LegalAction.CLI_SELECT in legal


def test_filter_creative_off_drops_ideate() -> None:
    legal = LegalActionFilter().legal_actions(
        _healthy_state(creative_mode_enabled=False)
    )
    assert LegalAction.IDEATE not in legal


def test_filter_creative_on_keeps_ideate() -> None:
    legal = LegalActionFilter().legal_actions(_healthy_state())
    assert LegalAction.IDEATE in legal


def test_filter_returns_frozenset() -> None:
    legal = LegalActionFilter().legal_actions(_healthy_state())
    assert isinstance(legal, frozenset)
    with pytest.raises(AttributeError):
        legal.add(LegalAction.WAIT)  # type: ignore[attr-defined]


def test_filter_combined_rules() -> None:
    """Quota + concurrency simultaneously drop TASK_START."""
    state = _healthy_state(
        active_concurrent_sessions=1,
        cli_quota={cli: _snap(cli_id=cli, used_pct=99.0) for cli in DEFAULT_CLI_IDS},
        creative_mode_enabled=False,
    )
    legal = LegalActionFilter().legal_actions(state)
    expected = frozenset(
        {
            LegalAction.SESSION_RESUME,
            LegalAction.KANBAN_SUGGEST,
            LegalAction.OPERATOR_ASK,
            LegalAction.WAIT,
            LegalAction.SELF_STOP,
        }
    )
    assert legal == expected


def test_filter_supervised_mode_does_not_alter_set_in_faz_b() -> None:
    """Faz B exposes the marker without acting on it; Faz G wraps the act."""
    legal_supervised = LegalActionFilter().legal_actions(
        _healthy_state(supervised_mode=True)
    )
    legal_unsupervised = LegalActionFilter().legal_actions(
        _healthy_state(supervised_mode=False)
    )
    assert legal_supervised == legal_unsupervised


# ── WorldStateBuilder ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_builder_degraded_with_no_dependencies(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True),
        pause_signal=pause,
    )
    state = await builder.build()
    assert state.pause_active is False
    assert state.within_active_hours is True
    assert state.active_concurrent_sessions == 0
    assert state.creative_mode_enabled is False
    assert state.supervised_mode is False
    assert state.last_active_workspace is None
    assert all(state.cli_quota[cli] is None for cli in DEFAULT_CLI_IDS)


@pytest.mark.asyncio
async def test_builder_reads_pause_signal(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    pause.request_pause(reason="test")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True),
        pause_signal=pause,
    )
    state = await builder.build()
    assert state.pause_active is True


@pytest.mark.asyncio
async def test_builder_quota_reader_populates_snapshots(tmp_path: Path) -> None:
    captured: list[str] = []

    async def fake_reader(cli_id: str) -> QuotaSnapshot | None:
        captured.append(cli_id)
        if cli_id == "claude-code":
            return _snap(cli_id=cli_id, used_pct=20.0)
        return None

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True),
        pause_signal=pause,
        quota_reader=fake_reader,
        cli_ids=("claude-code", "codex"),
    )
    state = await builder.build()
    assert state.cli_quota["claude-code"] is not None
    assert state.cli_quota["codex"] is None
    assert captured == ["claude-code", "codex"]


@pytest.mark.asyncio
async def test_builder_quota_reader_exception_degrades_to_none(
    tmp_path: Path,
) -> None:
    async def failing_reader(cli_id: str) -> QuotaSnapshot | None:
        msg = f"boom for {cli_id}"
        raise RuntimeError(msg)

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True),
        pause_signal=pause,
        quota_reader=failing_reader,
        cli_ids=("claude-code",),
    )
    state = await builder.build()
    assert state.cli_quota == {"claude-code": None}


@pytest.mark.asyncio
async def test_builder_concurrency_probe(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True, max_concurrency=3),
        pause_signal=pause,
        concurrency_probe=lambda: 2,
    )
    state = await builder.build()
    assert state.active_concurrent_sessions == 2
    assert state.max_concurrent_sessions == 3


@pytest.mark.asyncio
async def test_builder_creative_and_supervised_providers(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True),
        pause_signal=pause,
        creative_mode_provider=lambda: True,
        supervised_mode_provider=lambda: True,
    )
    state = await builder.build()
    assert state.creative_mode_enabled is True
    assert state.supervised_mode is True


@pytest.mark.asyncio
async def test_builder_within_active_hours_probe(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True),
        pause_signal=pause,
        within_active_hours_probe=lambda: False,
    )
    state = await builder.build()
    assert state.within_active_hours is False


@pytest.mark.asyncio
async def test_builder_talk_workspace_probe(tmp_path: Path) -> None:
    async def workspace_probe() -> str | None:
        return "beta"

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True),
        pause_signal=pause,
        talk_last_workspace_probe=workspace_probe,
    )
    state = await builder.build()
    assert state.last_active_workspace == "beta"


@pytest.mark.asyncio
async def test_builder_talk_workspace_probe_exception(tmp_path: Path) -> None:
    async def failing_probe() -> str | None:
        msg = "talk store offline"
        raise RuntimeError(msg)

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True),
        pause_signal=pause,
        talk_last_workspace_probe=failing_probe,
    )
    state = await builder.build()
    assert state.last_active_workspace is None


# ── S7 — workspace_eligible_probe gate (ADR-007 §4 S7) ───────────────────


@pytest.mark.asyncio
async def test_builder_workspace_gate_passes_eligible(tmp_path: Path) -> None:
    """Eligible workspace flows through unchanged."""

    async def talk_probe() -> str | None:
        return "alpha"

    async def eligible(_slug: str) -> bool:
        return True

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True),
        pause_signal=pause,
        talk_last_workspace_probe=talk_probe,
        workspace_eligible_probe=eligible,
    )
    state = await builder.build()
    assert state.last_active_workspace == "alpha"


@pytest.mark.asyncio
async def test_builder_workspace_gate_drops_ineligible(tmp_path: Path) -> None:
    """Ineligible workspace (paused or archived) is nulled out."""

    async def talk_probe() -> str | None:
        return "beta"

    async def ineligible(_slug: str) -> bool:
        return False

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True),
        pause_signal=pause,
        talk_last_workspace_probe=talk_probe,
        workspace_eligible_probe=ineligible,
    )
    state = await builder.build()
    assert state.last_active_workspace is None


@pytest.mark.asyncio
async def test_builder_workspace_gate_fails_open(tmp_path: Path) -> None:
    """A failing eligibility probe keeps the workspace (fail-OPEN
    matches the active-hours probe convention)."""

    async def talk_probe() -> str | None:
        return "gamma"

    async def boom(_slug: str) -> bool:
        msg = "project store offline"
        raise RuntimeError(msg)

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True),
        pause_signal=pause,
        talk_last_workspace_probe=talk_probe,
        workspace_eligible_probe=boom,
    )
    state = await builder.build()
    assert state.last_active_workspace == "gamma"


@pytest.mark.asyncio
async def test_builder_workspace_gate_no_op_when_no_talk_probe(
    tmp_path: Path,
) -> None:
    """When the talk probe is absent there is nothing to gate."""

    async def ineligible(_slug: str) -> bool:
        return False

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    builder = WorldStateBuilder(
        config=HeartbeatConfig(enabled=True),
        pause_signal=pause,
        workspace_eligible_probe=ineligible,
    )
    state = await builder.build()
    assert state.last_active_workspace is None
