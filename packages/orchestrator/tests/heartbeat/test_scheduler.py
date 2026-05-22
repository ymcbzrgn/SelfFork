"""S-Auto Faz A — HeartbeatScheduler daemon lifecycle + gate tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from selffork_orchestrator.heartbeat.actions import LegalAction
from selffork_orchestrator.heartbeat.config import (
    DEFAULT_RECONCILIATION_SECONDS,
    DEFAULT_TICK_SECONDS,
    DEFAULT_TIMEZONE,
    HeartbeatConfig,
    build_default_heartbeat,
    build_default_heartbeat_config,
)
from selffork_orchestrator.heartbeat.scheduler import (
    HeartbeatEvent,
    HeartbeatScheduler,
    HeartbeatState,
    _parse_hhmm,
)
from selffork_orchestrator.telegram.inbound_router import PauseSignal


def _enabled_config(**overrides: object) -> HeartbeatConfig:
    base: dict[str, object] = dict(
        enabled=True,
        tick_seconds=0.02,
        reconciliation_seconds=0.5,
        max_concurrency=1,
        active_hours="0:00-24:00",
        timezone=DEFAULT_TIMEZONE,
    )
    base.update(overrides)
    return HeartbeatConfig(**base)  # type: ignore[arg-type]


# ── lifecycle ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disabled_config_skips_start(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(
        config=HeartbeatConfig(enabled=False), pause_signal=pause
    )
    assert sched.state is HeartbeatState.DISABLED
    await sched.start()
    assert sched.state is HeartbeatState.DISABLED
    assert not sched.is_running


@pytest.mark.asyncio
async def test_disabled_stop_is_safe(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(
        config=HeartbeatConfig(enabled=False), pause_signal=pause
    )
    await sched.stop()
    assert sched.state is HeartbeatState.DISABLED


@pytest.mark.asyncio
async def test_start_stop_clean_transitions(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(config=_enabled_config(), pause_signal=pause)
    assert sched.state is HeartbeatState.INACTIVE
    await sched.start()
    assert sched.state is HeartbeatState.RUNNING
    assert sched.is_running
    await sched.stop()
    assert sched.state is HeartbeatState.STOPPED
    assert not sched.is_running


@pytest.mark.asyncio
async def test_start_is_idempotent(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(config=_enabled_config(), pause_signal=pause)
    await sched.start()
    first_task = sched._task
    await sched.start()
    assert sched._task is first_task
    assert sched.is_running
    await sched.stop()


@pytest.mark.asyncio
async def test_stop_is_idempotent(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(config=_enabled_config(), pause_signal=pause)
    await sched.start()
    await sched.stop()
    await sched.stop()
    assert sched.state is HeartbeatState.STOPPED


# ── event + reconciliation triggers ───────────────────────────────────


@pytest.mark.asyncio
async def test_event_drives_tick(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(config=_enabled_config(), pause_signal=pause)
    await sched.start()
    sched.submit_event(HeartbeatEvent.KANBAN_CHANGED)
    sched.submit_event(HeartbeatEvent.OPERATOR_MESSAGE)
    await asyncio.sleep(0.15)
    assert sched.tick_count >= 2
    await sched.stop()


@pytest.mark.asyncio
async def test_reconciliation_fires_without_events(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(
        config=_enabled_config(reconciliation_seconds=0.05),
        pause_signal=pause,
    )
    await sched.start()
    await asyncio.sleep(0.2)
    assert sched.tick_count >= 2
    await sched.stop()


@pytest.mark.asyncio
async def test_event_pre_start_drains_after_start(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(config=_enabled_config(), pause_signal=pause)
    sched.submit_event(HeartbeatEvent.SESSION_DONE)
    await sched.start()
    await asyncio.sleep(0.1)
    assert sched.tick_count >= 1
    await sched.stop()


# ── reactive gates (pause + active hours) ─────────────────────────────


@pytest.mark.asyncio
async def test_pause_signal_skips_decide(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    pause.request_pause(reason="test")
    sched = HeartbeatScheduler(
        config=_enabled_config(reconciliation_seconds=0.05),
        pause_signal=pause,
    )
    await sched.start()
    await asyncio.sleep(0.15)
    assert sched.tick_count == 0
    pause.clear()
    await asyncio.sleep(0.15)
    assert sched.tick_count >= 1
    await sched.stop()


@pytest.mark.asyncio
async def test_active_hours_24_7_default_keeps_running(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(
        config=_enabled_config(active_hours="0:00-24:00"),
        pause_signal=pause,
    )
    await sched.start()
    sched.submit_event(HeartbeatEvent.RECONCILIATION)
    await asyncio.sleep(0.1)
    assert sched.tick_count >= 1
    await sched.stop()


@pytest.mark.asyncio
async def test_active_hours_parse_failure_fails_open(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(
        config=_enabled_config(active_hours="invalid-spec"),
        pause_signal=pause,
    )
    await sched.start()
    sched.submit_event(HeartbeatEvent.KANBAN_CHANGED)
    await asyncio.sleep(0.1)
    assert sched.tick_count >= 1
    await sched.stop()


# ── HH:MM parser ──────────────────────────────────────────────────────


def test_parse_hhmm_boundaries() -> None:
    assert _parse_hhmm("0:00") == 0
    assert _parse_hhmm("00:00") == 0
    assert _parse_hhmm("06:30") == 6 * 60 + 30
    assert _parse_hhmm("22:00") == 22 * 60
    assert _parse_hhmm("23:59") == 23 * 60 + 59
    assert _parse_hhmm("24:00") == 24 * 60


def test_parse_hhmm_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        _parse_hhmm("25:00")
    with pytest.raises(ValueError):
        _parse_hhmm("12:60")
    with pytest.raises(ValueError):
        _parse_hhmm("not-a-time")
    with pytest.raises(ValueError):
        _parse_hhmm("12")


# ── config env resolution ─────────────────────────────────────────────


_ENV_KEYS = (
    "SELFFORK_HEARTBEAT_ENABLED",
    "SELFFORK_HEARTBEAT_TICK_SECONDS",
    "SELFFORK_HEARTBEAT_RECONCILIATION_SECONDS",
    "SELFFORK_HEARTBEAT_MAX_CONCURRENCY",
    "SELFFORK_HEARTBEAT_ACTIVE_HOURS",
    "SELFFORK_HEARTBEAT_TIMEZONE",
)


def _clear_heartbeat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_config_env_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_heartbeat_env(monkeypatch)
    monkeypatch.setenv("SELFFORK_HEARTBEAT_ENABLED", "true")
    monkeypatch.setenv("SELFFORK_HEARTBEAT_TICK_SECONDS", "0.5")
    monkeypatch.setenv("SELFFORK_HEARTBEAT_RECONCILIATION_SECONDS", "300")
    monkeypatch.setenv("SELFFORK_HEARTBEAT_MAX_CONCURRENCY", "3")
    monkeypatch.setenv("SELFFORK_HEARTBEAT_ACTIVE_HOURS", "8:00-22:00")
    monkeypatch.setenv("SELFFORK_HEARTBEAT_TIMEZONE", "Europe/Istanbul")
    config = build_default_heartbeat_config()
    assert config.enabled is True
    assert config.tick_seconds == 0.5
    assert config.reconciliation_seconds == 300.0
    assert config.max_concurrency == 3
    assert config.active_hours == "8:00-22:00"
    assert config.timezone == "Europe/Istanbul"


def test_config_env_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_heartbeat_env(monkeypatch)
    config = build_default_heartbeat_config()
    assert config.enabled is False
    assert config.tick_seconds == DEFAULT_TICK_SECONDS
    assert config.reconciliation_seconds == DEFAULT_RECONCILIATION_SECONDS
    assert config.max_concurrency == 1
    assert config.active_hours == "0:00-24:00"
    assert config.timezone == DEFAULT_TIMEZONE


def test_config_invalid_env_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_heartbeat_env(monkeypatch)
    monkeypatch.setenv("SELFFORK_HEARTBEAT_TICK_SECONDS", "not-a-float")
    monkeypatch.setenv("SELFFORK_HEARTBEAT_MAX_CONCURRENCY", "-5")
    monkeypatch.setenv("SELFFORK_HEARTBEAT_TIMEZONE", "Mars/OlympusMons")
    config = build_default_heartbeat_config()
    assert config.tick_seconds == DEFAULT_TICK_SECONDS
    assert config.max_concurrency == 1
    assert config.timezone == DEFAULT_TIMEZONE


def test_config_enabled_accepts_true_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_heartbeat_env(monkeypatch)
    for alias in ("true", "1", "yes", "TRUE", "Yes"):
        monkeypatch.setenv("SELFFORK_HEARTBEAT_ENABLED", alias)
        assert build_default_heartbeat_config().enabled is True


def test_config_enabled_rejects_falsy(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_heartbeat_env(monkeypatch)
    for alias in ("false", "0", "no", "off", "", "garbage"):
        monkeypatch.setenv("SELFFORK_HEARTBEAT_ENABLED", alias)
        assert build_default_heartbeat_config().enabled is False


def test_build_default_heartbeat_returns_scheduler(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clear_heartbeat_env(monkeypatch)
    sched = build_default_heartbeat()
    assert isinstance(sched, HeartbeatScheduler)
    # Default opt-in disabled — daemon lands in DISABLED.
    assert sched.state is HeartbeatState.DISABLED


# ── Faz B filter integration ───────────────────────────────────────


@pytest.mark.asyncio
async def test_decide_tick_populates_last_legal_actions(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(config=_enabled_config(), pause_signal=pause)
    assert sched.last_legal_actions is None
    await sched.start()
    sched.submit_event(HeartbeatEvent.KANBAN_CHANGED)
    await asyncio.sleep(0.1)
    legal = sched.last_legal_actions
    assert legal is not None
    # Default WorldStateBuilder has no creative_mode_provider → IDEATE
    # drops out (Faz F default pre-M7 — operator opts in via Settings).
    assert LegalAction.IDEATE not in legal
    # No quota signal + no concurrency probe ⇒ TASK_START still legal.
    assert LegalAction.TASK_START in legal
    assert LegalAction.WAIT in legal
    await sched.stop()


@pytest.mark.asyncio
async def test_pause_short_circuit_skips_filter(tmp_path: Path) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    pause.request_pause(reason="test")
    sched = HeartbeatScheduler(
        config=_enabled_config(reconciliation_seconds=0.05),
        pause_signal=pause,
    )
    await sched.start()
    await asyncio.sleep(0.15)
    # Scheduler short-circuits BEFORE the filter is invoked — so
    # ``last_legal_actions`` stays None even though the daemon is
    # running.
    assert sched.last_legal_actions is None
    await sched.stop()


# ── Faz C deliberation integration ─────────────────────────────────


@pytest.mark.asyncio
async def test_decide_tick_populates_action_decision(tmp_path: Path) -> None:
    from collections.abc import Mapping, Sequence

    from selffork_orchestrator.heartbeat.deliberation import DeliberationLayer

    class _StubSpeaker:
        async def reply(
            self, messages: Sequence[Mapping[str, str]]
        ) -> str:
            return '{"action": "bekle", "reasoning": "şu an iş yok"}'

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    deliberation = DeliberationLayer(speaker=_StubSpeaker())
    sched = HeartbeatScheduler(
        config=_enabled_config(),
        pause_signal=pause,
        deliberation_layer=deliberation,
    )
    await sched.start()
    sched.submit_event(HeartbeatEvent.KANBAN_CHANGED)
    await asyncio.sleep(0.1)
    decision = sched.last_action_decision
    assert decision is not None
    assert decision.action is LegalAction.WAIT
    assert decision.reasoning == "şu an iş yok"
    assert decision.fallback is False
    await sched.stop()


@pytest.mark.asyncio
async def test_decide_tick_without_deliberation_keeps_legal_only(
    tmp_path: Path,
) -> None:
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(config=_enabled_config(), pause_signal=pause)
    await sched.start()
    sched.submit_event(HeartbeatEvent.KANBAN_CHANGED)
    await asyncio.sleep(0.1)
    assert sched.last_legal_actions is not None
    assert sched.last_action_decision is None
    await sched.stop()


def test_build_default_heartbeat_wires_deliberation_when_endpoint_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_heartbeat_env(monkeypatch)
    monkeypatch.setenv(
        "SELFFORK_TALK_MODEL_ENDPOINT", "http://127.0.0.1:8080/v1"
    )
    monkeypatch.setenv("SELFFORK_TALK_MODEL", "gemma-4-e2b")
    sched = build_default_heartbeat()
    assert sched._deliberation is not None

def test_build_default_heartbeat_skips_deliberation_when_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_heartbeat_env(monkeypatch)
    monkeypatch.delenv("SELFFORK_TALK_MODEL_ENDPOINT", raising=False)
    monkeypatch.delenv("SELFFORK_TALK_MODEL", raising=False)
    sched = build_default_heartbeat()
    assert sched._deliberation is None


def test_build_default_heartbeat_always_wires_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_heartbeat_env(monkeypatch)
    sched = build_default_heartbeat()
    assert sched._executor is not None


# ── Faz D executor integration ─────────────────────────────────────


@pytest.mark.asyncio
async def test_decide_tick_with_executor_populates_action_result(
    tmp_path: Path,
) -> None:
    from collections.abc import Mapping, Sequence

    from selffork_orchestrator.heartbeat.deliberation import DeliberationLayer
    from selffork_orchestrator.heartbeat.executor import ActionExecutor

    class _StubSpeaker:
        async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
            return '{"action": "bekle", "reasoning": "iş yok"}'

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(
        config=_enabled_config(),
        pause_signal=pause,
        deliberation_layer=DeliberationLayer(speaker=_StubSpeaker()),
        action_executor=ActionExecutor(),
    )
    await sched.start()
    sched.submit_event(HeartbeatEvent.KANBAN_CHANGED)
    await asyncio.sleep(0.1)
    result = sched.last_action_result
    assert result is not None
    assert result.action is LegalAction.WAIT
    assert result.outcome == "executed"
    await sched.stop()


@pytest.mark.asyncio
async def test_restart_after_self_stop_resumes_ticking(tmp_path: Path) -> None:
    """Audit fix #1: start() must reset _self_stop_requested so an
    in-process restart actually spins up a working tick loop."""
    from collections.abc import Mapping, Sequence

    from selffork_orchestrator.heartbeat.deliberation import DeliberationLayer
    from selffork_orchestrator.heartbeat.executor import ActionExecutor

    class _SelfStopOnceSpeaker:
        def __init__(self) -> None:
            self.calls = 0

        async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
            self.calls += 1
            if self.calls == 1:
                return (
                    '{"action": "kendini_durdur", '
                    '"reasoning": "first run stop"}'
                )
            return '{"action": "bekle", "reasoning": "second run idle"}'

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    speaker = _SelfStopOnceSpeaker()
    sched = HeartbeatScheduler(
        config=_enabled_config(),
        pause_signal=pause,
        deliberation_layer=DeliberationLayer(speaker=speaker),
        action_executor=ActionExecutor(),
    )

    await sched.start()
    sched.submit_event(HeartbeatEvent.KANBAN_CHANGED)
    await asyncio.sleep(0.2)
    assert sched.state is HeartbeatState.STOPPED

    # Restart in-process — the new tick loop must accept events again.
    await sched.start()
    assert sched.state is HeartbeatState.RUNNING
    sched.submit_event(HeartbeatEvent.OPERATOR_MESSAGE)
    await asyncio.sleep(0.2)
    assert sched.tick_count >= 1
    assert (
        sched.last_action_decision is not None
        and sched.last_action_decision.action is LegalAction.WAIT
    )
    await sched.stop()


@pytest.mark.asyncio
async def test_self_stop_action_exits_loop_cleanly(tmp_path: Path) -> None:
    from collections.abc import Mapping, Sequence

    from selffork_orchestrator.heartbeat.deliberation import DeliberationLayer
    from selffork_orchestrator.heartbeat.executor import ActionExecutor

    class _SelfStopSpeaker:
        async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
            return '{"action": "kendini_durdur", "reasoning": "operator paused"}'

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(
        config=_enabled_config(),
        pause_signal=pause,
        deliberation_layer=DeliberationLayer(speaker=_SelfStopSpeaker()),
        action_executor=ActionExecutor(),
    )
    await sched.start()
    sched.submit_event(HeartbeatEvent.OPERATOR_MESSAGE)
    await asyncio.sleep(0.2)
    assert sched.state is HeartbeatState.STOPPED
    assert sched.last_action_decision is not None
    assert sched.last_action_decision.action is LegalAction.SELF_STOP


@pytest.mark.asyncio
async def test_executor_without_deliberation_is_not_called(
    tmp_path: Path,
) -> None:
    from selffork_orchestrator.heartbeat.executor import ActionExecutor

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(
        config=_enabled_config(),
        pause_signal=pause,
        action_executor=ActionExecutor(),
        # No deliberation — executor is not invoked.
    )
    await sched.start()
    sched.submit_event(HeartbeatEvent.KANBAN_CHANGED)
    await asyncio.sleep(0.1)
    assert sched.last_action_result is None
    await sched.stop()


# ── Faz E audit + checkpoint + AIR integration ────────────────────


@pytest.mark.asyncio
async def test_audit_writer_records_tick_to_disk(tmp_path: Path) -> None:
    from collections.abc import Mapping, Sequence

    from selffork_orchestrator.heartbeat.audit import AuditWriter
    from selffork_orchestrator.heartbeat.deliberation import DeliberationLayer
    from selffork_orchestrator.heartbeat.executor import ActionExecutor

    class _StubSpeaker:
        async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
            return '{"action": "bekle", "reasoning": "iş yok"}'

    audit_path = tmp_path / "audit.jsonl"
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(
        config=_enabled_config(),
        pause_signal=pause,
        deliberation_layer=DeliberationLayer(speaker=_StubSpeaker()),
        action_executor=ActionExecutor(),
        audit_writer=AuditWriter(path=audit_path),
    )
    await sched.start()
    sched.submit_event(HeartbeatEvent.KANBAN_CHANGED)
    await asyncio.sleep(0.1)
    await sched.stop()
    assert audit_path.is_file()
    lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 1
    import json
    payload = json.loads(lines[0])
    assert payload["decision_action"] == "bekle"
    assert payload["result_outcome"] == "executed"


@pytest.mark.asyncio
async def test_checkpoint_writer_refreshes_per_tick(tmp_path: Path) -> None:
    from collections.abc import Mapping, Sequence

    from selffork_orchestrator.heartbeat.checkpoint import CheckpointWriter
    from selffork_orchestrator.heartbeat.deliberation import DeliberationLayer
    from selffork_orchestrator.heartbeat.executor import ActionExecutor

    class _StubSpeaker:
        async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
            return '{"action": "bekle", "reasoning": "x"}'

    ck_path = tmp_path / "checkpoint.json"
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(
        config=_enabled_config(),
        pause_signal=pause,
        deliberation_layer=DeliberationLayer(speaker=_StubSpeaker()),
        action_executor=ActionExecutor(),
        checkpoint_writer=CheckpointWriter(path=ck_path),
    )
    await sched.start()
    sched.submit_event(HeartbeatEvent.KANBAN_CHANGED)
    await asyncio.sleep(0.1)
    await sched.stop()
    assert ck_path.is_file()
    loaded = CheckpointWriter(path=ck_path).read()
    assert loaded is not None
    assert loaded.next_action in {"bekle", "kendini_durdur"}


@pytest.mark.asyncio
async def test_air_detector_panic_halts_daemon(tmp_path: Path) -> None:
    from collections.abc import Mapping, Sequence

    from selffork_orchestrator.heartbeat.air import AIRDetector
    from selffork_orchestrator.heartbeat.deliberation import DeliberationLayer
    from selffork_orchestrator.heartbeat.executor import ActionExecutor

    class _PanicSpeaker:
        async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
            return (
                '{"action": "bekle", '
                '"reasoning": "I am panicking and covering up the failure"}'
            )

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(
        config=_enabled_config(),
        pause_signal=pause,
        deliberation_layer=DeliberationLayer(speaker=_PanicSpeaker()),
        action_executor=ActionExecutor(),
        air_detector=AIRDetector(),
    )
    await sched.start()
    sched.submit_event(HeartbeatEvent.OPERATOR_MESSAGE)
    await asyncio.sleep(0.2)
    # AIR detected panic → daemon self-stopped.
    assert sched.state is HeartbeatState.STOPPED
    assert sched.last_air_alert is not None
    assert sched.last_air_alert.severity in {"high", "critical"}


@pytest.mark.asyncio
async def test_air_alert_dispatches_to_emergency_bridge(tmp_path: Path) -> None:
    from collections.abc import Mapping, Sequence
    from datetime import UTC, datetime

    from selffork_orchestrator.heartbeat.air import AIRDetector
    from selffork_orchestrator.heartbeat.deliberation import DeliberationLayer
    from selffork_orchestrator.heartbeat.executor import ActionExecutor
    from selffork_orchestrator.telegram.bridge import (
        DeliveryAttempt,
        TelegramBridge,
        TelegramMessage,
    )

    class _PanicSpeaker:
        async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
            return '{"action": "bekle", "reasoning": "I am panicking"}'

    class _RecordingBridge(TelegramBridge):
        def __init__(self) -> None:
            self.messages: list[TelegramMessage] = []

        async def notify(
            self, message: TelegramMessage
        ) -> DeliveryAttempt:
            self.messages.append(message)
            return DeliveryAttempt(
                delivered=True, chat_id=1, sent_at=datetime.now(UTC)
            )

    bridge = _RecordingBridge()
    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    sched = HeartbeatScheduler(
        config=_enabled_config(),
        pause_signal=pause,
        deliberation_layer=DeliberationLayer(speaker=_PanicSpeaker()),
        action_executor=ActionExecutor(),
        air_detector=AIRDetector(),
        emergency_telegram_bridge=bridge,
    )
    await sched.start()
    sched.submit_event(HeartbeatEvent.OPERATOR_MESSAGE)
    await asyncio.sleep(0.2)
    assert len(bridge.messages) >= 1
    msg = bridge.messages[0]
    assert msg.level == "crit"
    assert "AIR Alert" in msg.text
    assert msg.session_id == "heartbeat-air"
