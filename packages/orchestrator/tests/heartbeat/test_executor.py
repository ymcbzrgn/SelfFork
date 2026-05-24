"""S-Auto Faz D — ActionExecutor tests (8 closed-vocabulary actions)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from selffork_orchestrator.heartbeat.actions import LegalAction
from selffork_orchestrator.heartbeat.deliberation import ActionDecision
from selffork_orchestrator.heartbeat.executor import (
    ActionExecutor,
    ActionResult,
)
from selffork_orchestrator.heartbeat.filter import (
    DEFAULT_CLI_IDS,
    DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT,
    WorldState,
)
from selffork_orchestrator.telegram.bridge import (
    DeliveryAttempt,
    NullTelegramBridge,
    TelegramBridge,
    TelegramMessage,
)
from selffork_shared.quota import QuotaSnapshot, WindowKind, WindowState

# ── Fixtures ─────────────────────────────────────────────────────────


def _quota(cli_id: str, used_pct: float = 25.0) -> QuotaSnapshot:
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


def _state(**overrides: object) -> WorldState:
    base: dict[str, object] = dict(
        pause_active=False,
        within_active_hours=True,
        active_concurrent_sessions=0,
        max_concurrent_sessions=1,
        creative_mode_enabled=False,
        cli_quota={cli: _quota(cli) for cli in DEFAULT_CLI_IDS},
        quota_exhaustion_threshold_pct=DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT,
        supervised_mode=False,
        last_active_workspace="alpha",
    )
    base.update(overrides)
    return WorldState(**base)  # type: ignore[arg-type]


def _decision(action: LegalAction, reasoning: str = "test reasoning") -> ActionDecision:
    return ActionDecision(action=action, reasoning=reasoning)


# ── Pure-handler outcomes (no side effects) ─────────────────────────


@pytest.mark.asyncio
async def test_wait_records_quiet_tick() -> None:
    executor = ActionExecutor()
    result = await executor.execute(
        _decision(LegalAction.WAIT, "şu an iş yok"), _state()
    )
    assert result.action is LegalAction.WAIT
    assert result.outcome == "executed"
    assert result.summary == "şu an iş yok"


@pytest.mark.asyncio
async def test_wait_uses_default_summary_when_reasoning_empty() -> None:
    executor = ActionExecutor()
    result = await executor.execute(_decision(LegalAction.WAIT, ""), _state())
    assert result.summary == "quiet tick"


@pytest.mark.asyncio
async def test_self_stop_signals_executor() -> None:
    executor = ActionExecutor()
    result = await executor.execute(
        _decision(LegalAction.SELF_STOP, "operator paused"), _state()
    )
    assert result.action is LegalAction.SELF_STOP
    assert result.outcome == "executed"


@pytest.mark.asyncio
async def test_session_resume_defers() -> None:
    executor = ActionExecutor()
    result = await executor.execute(_decision(LegalAction.SESSION_RESUME), _state())
    assert result.outcome == "deferred"
    assert result.action is LegalAction.SESSION_RESUME


@pytest.mark.asyncio
async def test_cli_select_skipped_when_unwired() -> None:
    # S6: no cli_selector wired ⇒ skipped (was a deferred stub pre-S6).
    executor = ActionExecutor()
    result = await executor.execute(_decision(LegalAction.CLI_SELECT, ""), _state())
    assert result.outcome == "skipped"
    assert "not wired" in result.summary


@pytest.mark.asyncio
async def test_cli_select_executes_with_selector() -> None:
    # S6: a wired cli_selector picks a (cli, model) + effort; the
    # selection metadata lands on the ActionResult (audit observability).
    from selffork_orchestrator.heartbeat.executor import CliSelectionOutcome

    async def _selector(state: WorldState) -> CliSelectionOutcome:
        return CliSelectionOutcome(
            cli="codex",
            reasoning=(
                f"affinity → codex/gpt-5.5 for {state.last_active_workspace}"
            ),
            metadata={
                "chosen_cli": "codex",
                "chosen_model": "gpt-5.5",
                "effort": "high",
            },
        )

    executor = ActionExecutor(cli_selector=_selector)
    result = await executor.execute(_decision(LegalAction.CLI_SELECT, ""), _state())
    assert result.outcome == "executed"
    assert result.action is LegalAction.CLI_SELECT
    assert result.metadata["chosen_model"] == "gpt-5.5"


@pytest.mark.asyncio
async def test_cli_select_skipped_when_no_eligible_cli() -> None:
    # S6: selector returns cli=None (fleet-wide quota exhaustion) ⇒ skipped.
    from selffork_orchestrator.heartbeat.executor import CliSelectionOutcome

    async def _selector(state: WorldState) -> CliSelectionOutcome:
        return CliSelectionOutcome(
            cli=None,
            reasoning="all CLIs quota-exhausted",
            metadata={"quota_exhausted": True},
        )

    executor = ActionExecutor(cli_selector=_selector)
    result = await executor.execute(_decision(LegalAction.CLI_SELECT, ""), _state())
    assert result.outcome == "skipped"


@pytest.mark.asyncio
async def test_ideate_defers() -> None:
    executor = ActionExecutor()
    result = await executor.execute(_decision(LegalAction.IDEATE, ""), _state())
    assert result.outcome == "deferred"
    assert "Faz F" in result.summary or "Yaratma" in result.summary


# ── OPERATOR_ASK ────────────────────────────────────────────────────


class _RecordingBridge(TelegramBridge):
    def __init__(
        self,
        *,
        delivered: bool = True,
        reason: str | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self.delivered = delivered
        self.reason = reason
        self.raise_exc = raise_exc
        self.messages: list[TelegramMessage] = []

    async def notify(self, message: TelegramMessage) -> DeliveryAttempt:
        self.messages.append(message)
        if self.raise_exc is not None:
            raise self.raise_exc
        return DeliveryAttempt(
            delivered=self.delivered,
            reason=self.reason,
            chat_id=42 if self.delivered else None,
            sent_at=datetime.now(tz=UTC),
        )


@pytest.mark.asyncio
async def test_operator_ask_without_bridge_skips() -> None:
    executor = ActionExecutor(telegram_bridge=None)
    result = await executor.execute(
        _decision(LegalAction.OPERATOR_ASK, "Supabase key gerekli"),
        _state(),
    )
    assert result.outcome == "skipped"
    assert "not wired" in result.summary


@pytest.mark.asyncio
async def test_operator_ask_delivers_message_to_bridge() -> None:
    bridge = _RecordingBridge(delivered=True)
    executor = ActionExecutor(telegram_bridge=bridge)
    result = await executor.execute(
        _decision(LegalAction.OPERATOR_ASK, "Supabase key gerekli"),
        _state(),
    )
    assert result.outcome == "executed"
    assert result.metadata["delivered"] is True
    assert result.metadata["chat_id"] == 42
    assert len(bridge.messages) == 1
    msg = bridge.messages[0]
    assert "Self Jr" in msg.text
    assert "Supabase key gerekli" in msg.text
    assert msg.project_slug == "alpha"
    assert msg.session_id == "heartbeat"
    assert msg.level == "info"


@pytest.mark.asyncio
async def test_operator_ask_undelivered_fails() -> None:
    bridge = _RecordingBridge(delivered=False, reason="rate limited")
    executor = ActionExecutor(telegram_bridge=bridge)
    result = await executor.execute(
        _decision(LegalAction.OPERATOR_ASK, "x"),
        _state(),
    )
    assert result.outcome == "failed"
    assert "rate limited" in result.summary
    assert result.metadata["delivered"] is False


@pytest.mark.asyncio
async def test_operator_ask_bridge_raises_fails() -> None:
    bridge = _RecordingBridge(raise_exc=RuntimeError("network down"))
    executor = ActionExecutor(telegram_bridge=bridge)
    result = await executor.execute(
        _decision(LegalAction.OPERATOR_ASK, "x"),
        _state(),
    )
    assert result.outcome == "failed"
    assert "network down" in result.summary


@pytest.mark.asyncio
async def test_operator_ask_null_bridge_treated_as_undelivered() -> None:
    executor = ActionExecutor(telegram_bridge=NullTelegramBridge())
    result = await executor.execute(
        _decision(LegalAction.OPERATOR_ASK, "x"),
        _state(),
    )
    assert result.outcome == "failed"


# ── TASK_START ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_task_start_without_starter_skips() -> None:
    executor = ActionExecutor(task_starter=None)
    result = await executor.execute(_decision(LegalAction.TASK_START), _state())
    assert result.outcome == "skipped"


@pytest.mark.asyncio
async def test_task_start_without_workspace_skips() -> None:
    async def starter(project: str, prd: str) -> int | None:
        return 999

    executor = ActionExecutor(task_starter=starter)
    result = await executor.execute(
        _decision(LegalAction.TASK_START),
        _state(last_active_workspace=None),
    )
    assert result.outcome == "skipped"
    assert "no active workspace" in result.summary


@pytest.mark.asyncio
async def test_task_start_calls_starter_with_workspace_and_prd() -> None:
    captured: dict[str, str] = {}

    async def starter(project: str, prd: str) -> int | None:
        captured["project"] = project
        captured["prd"] = prd
        return 12345

    executor = ActionExecutor(task_starter=starter)
    result = await executor.execute(
        _decision(LegalAction.TASK_START, "Login flow ekle"),
        _state(last_active_workspace="beta"),
    )
    assert result.outcome == "executed"
    assert result.metadata["pid"] == 12345
    assert result.metadata["project_slug"] == "beta"
    assert captured == {"project": "beta", "prd": "Login flow ekle"}


@pytest.mark.asyncio
async def test_task_start_starter_returns_none_fails() -> None:
    async def starter(project: str, prd: str) -> int | None:
        return None

    executor = ActionExecutor(task_starter=starter)
    result = await executor.execute(
        _decision(LegalAction.TASK_START),
        _state(),
    )
    assert result.outcome == "failed"
    assert "None pid" in result.summary


@pytest.mark.asyncio
async def test_task_start_starter_raises_fails() -> None:
    async def starter(project: str, prd: str) -> int | None:
        msg = "spawn failed"
        raise RuntimeError(msg)

    executor = ActionExecutor(task_starter=starter)
    result = await executor.execute(
        _decision(LegalAction.TASK_START),
        _state(),
    )
    assert result.outcome == "failed"
    assert "spawn failed" in result.summary


# ── KANBAN_SUGGEST ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kanban_suggest_without_creator_skips() -> None:
    executor = ActionExecutor(kanban_card_creator=None)
    result = await executor.execute(
        _decision(LegalAction.KANBAN_SUGGEST), _state()
    )
    assert result.outcome == "skipped"


@pytest.mark.asyncio
async def test_kanban_suggest_without_workspace_skips() -> None:
    async def creator(project: str, title: str, body: str) -> str:
        return "card-1"

    executor = ActionExecutor(kanban_card_creator=creator)
    result = await executor.execute(
        _decision(LegalAction.KANBAN_SUGGEST),
        _state(last_active_workspace=None),
    )
    assert result.outcome == "skipped"


@pytest.mark.asyncio
async def test_kanban_suggest_calls_creator_with_title_and_body() -> None:
    captured: dict[str, str] = {}

    async def creator(project: str, title: str, body: str) -> str:
        captured["project"] = project
        captured["title"] = title
        captured["body"] = body
        return "card-abc"

    executor = ActionExecutor(kanban_card_creator=creator)
    reasoning = "Login refactor lazım. Detay: oauth flow yeniden yazılmalı."
    result = await executor.execute(
        _decision(LegalAction.KANBAN_SUGGEST, reasoning),
        _state(last_active_workspace="gamma"),
    )
    assert result.outcome == "executed"
    assert result.metadata["card_id"] == "card-abc"
    assert captured["project"] == "gamma"
    assert captured["title"] == "Login refactor lazım"
    assert captured["body"] == reasoning


@pytest.mark.asyncio
async def test_kanban_suggest_empty_reasoning_uses_default_title() -> None:
    captured: dict[str, str] = {}

    async def creator(project: str, title: str, body: str) -> str:
        captured["title"] = title
        return "card-x"

    executor = ActionExecutor(kanban_card_creator=creator)
    result = await executor.execute(
        _decision(LegalAction.KANBAN_SUGGEST, ""),
        _state(),
    )
    assert result.outcome == "executed"
    assert captured["title"] == "Self Jr suggestion"


@pytest.mark.asyncio
async def test_kanban_suggest_creator_raises_fails() -> None:
    async def creator(project: str, title: str, body: str) -> str:
        msg = "kanban write failed"
        raise OSError(msg)

    executor = ActionExecutor(kanban_card_creator=creator)
    result = await executor.execute(
        _decision(LegalAction.KANBAN_SUGGEST, "x"),
        _state(),
    )
    assert result.outcome == "failed"
    assert "kanban write failed" in result.summary


# ── ActionResult shape ──────────────────────────────────────────────


def test_action_result_is_frozen() -> None:
    result = ActionResult(
        action=LegalAction.WAIT, outcome="executed", summary="ok"
    )
    with pytest.raises(AttributeError):
        result.summary = "edited"  # type: ignore[misc]


def test_action_result_metadata_default_empty() -> None:
    result = ActionResult(
        action=LegalAction.WAIT, outcome="executed", summary="ok"
    )
    assert result.metadata == {}


def test_action_result_default_executed_at_utc() -> None:
    result = ActionResult(
        action=LegalAction.WAIT, outcome="executed", summary="ok"
    )
    assert result.executed_at.tzinfo is UTC
