"""S-Auto Faz C — DeliberationLayer tests."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

import pytest

from selffork_orchestrator.heartbeat.actions import LegalAction
from selffork_orchestrator.heartbeat.deliberation import (
    DELIBERATION_SYSTEM_PROMPT,
    ActionDecision,
    DeliberationLayer,
    DeliberationParseError,
    _parse_decision,
)
from selffork_orchestrator.heartbeat.filter import (
    DEFAULT_CLI_IDS,
    DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT,
    WorldState,
)
from selffork_shared.errors import RuntimeUnhealthyError, SpeakerStalledError
from selffork_shared.quota import QuotaSnapshot, WindowKind, WindowState

# ── Fixtures ─────────────────────────────────────────────────────────


class _StubSpeaker:
    """Minimal Speaker stub that records calls and returns canned replies."""

    def __init__(
        self,
        *,
        reply_text: str = "",
        exception: Exception | None = None,
    ) -> None:
        self._reply_text = reply_text
        self._exception = exception
        self.calls: list[list[dict[str, str]]] = []

    async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
        self.calls.append([dict(m) for m in messages])
        if self._exception is not None:
            raise self._exception
        return self._reply_text


class _SlowReplySpeaker:
    """Speaker whose reply sleeps — exercises the per-tick budget timeout."""

    def __init__(
        self, *, delay_seconds: float, reply_text: str = "{}"
    ) -> None:
        self._delay = delay_seconds
        self._reply_text = reply_text

    async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
        await asyncio.sleep(self._delay)
        return self._reply_text


def _quota(cli_id: str, used_pct: float) -> QuotaSnapshot:
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
        cli_quota={cli: _quota(cli, 25.0) for cli in DEFAULT_CLI_IDS},
        quota_exhaustion_threshold_pct=DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT,
        supervised_mode=False,
        last_active_workspace="alpha",
    )
    base.update(overrides)
    return WorldState(**base)  # type: ignore[arg-type]


_FULL_LEGAL = frozenset(LegalAction)


# ── ActionDecision ───────────────────────────────────────────────────


def test_action_decision_defaults_to_now_utc() -> None:
    decision = ActionDecision(action=LegalAction.WAIT, reasoning="quiet tick")
    assert decision.action is LegalAction.WAIT
    assert decision.reasoning == "quiet tick"
    assert decision.selected_at.tzinfo is UTC
    assert decision.fallback is False


def test_action_decision_is_frozen() -> None:
    decision = ActionDecision(action=LegalAction.WAIT, reasoning="r")
    with pytest.raises(AttributeError):
        decision.reasoning = "edited"  # type: ignore[misc]


# ── Happy paths ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_select_parses_fenced_json_reply() -> None:
    speaker = _StubSpeaker(
        reply_text=(
            "Önce kanban'a baktım. ```json\n"
            '{"action": "task_başlat", "reasoning": "Beta projesinde önemli kart var."}\n'
            "```"
        )
    )
    layer = DeliberationLayer(speaker=speaker)
    decision = await layer.select(
        legal_actions=_FULL_LEGAL, world_state=_state()
    )
    assert decision.action is LegalAction.TASK_START
    assert decision.reasoning == "Beta projesinde önemli kart var."
    assert decision.fallback is False
    # System + user message both delivered.
    assert len(speaker.calls) == 1
    msgs = speaker.calls[0]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == DELIBERATION_SYSTEM_PROMPT
    assert msgs[1]["role"] == "user"
    assert "Legal actions" in msgs[1]["content"]


@pytest.mark.asyncio
async def test_select_parses_bare_json_reply() -> None:
    speaker = _StubSpeaker(
        reply_text='Karar: {"action": "bekle", "reasoning": "Şu an iş yok."}'
    )
    layer = DeliberationLayer(speaker=speaker)
    decision = await layer.select(
        legal_actions=_FULL_LEGAL, world_state=_state()
    )
    assert decision.action is LegalAction.WAIT
    assert decision.reasoning == "Şu an iş yok."


@pytest.mark.asyncio
async def test_select_handles_alternate_action_value() -> None:
    speaker = _StubSpeaker(
        reply_text=(
            '```json\n{"action": "operatöre_sor", '
            '"reasoning": "API key gerekli."}\n```'
        )
    )
    layer = DeliberationLayer(speaker=speaker)
    decision = await layer.select(
        legal_actions=_FULL_LEGAL, world_state=_state()
    )
    assert decision.action is LegalAction.OPERATOR_ASK


# ── Fallback paths ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_select_empty_legal_set_falls_back() -> None:
    speaker = _StubSpeaker(reply_text='{"action": "bekle", "reasoning": "n"}')
    layer = DeliberationLayer(speaker=speaker)
    decision = await layer.select(
        legal_actions=frozenset(), world_state=_state()
    )
    assert decision.action is LegalAction.WAIT
    assert decision.fallback is True
    # Speaker not called when legal set is empty.
    assert speaker.calls == []


@pytest.mark.asyncio
async def test_select_speaker_unhealthy_falls_back() -> None:
    speaker = _StubSpeaker(
        exception=RuntimeUnhealthyError("endpoint refused")
    )
    layer = DeliberationLayer(speaker=speaker)
    decision = await layer.select(
        legal_actions=_FULL_LEGAL, world_state=_state()
    )
    assert decision.action is LegalAction.WAIT
    assert decision.fallback is True
    # Unreachable ≠ stalled — the model was never even contacted.
    assert decision.stalled is False
    assert "speaker unreachable" in decision.reasoning


# ── ADR-011 §3.4 — stalled / per-tick-budget fallbacks ──────────────


@pytest.mark.asyncio
async def test_select_stalled_on_speaker_stalled() -> None:
    """Idle-token watchdog (SpeakerStalledError) → stalled WAIT."""
    speaker = _StubSpeaker(
        exception=SpeakerStalledError("no tokens for 90s — wedged")
    )
    layer = DeliberationLayer(speaker=speaker)
    decision = await layer.select(
        legal_actions=_FULL_LEGAL, world_state=_state()
    )
    assert decision.action is LegalAction.WAIT
    assert decision.fallback is True
    assert decision.stalled is True
    assert "stalled" in decision.reasoning


@pytest.mark.asyncio
async def test_select_stalled_on_budget_exceeded() -> None:
    """A slow-but-producing model past the per-tick budget → stalled WAIT.

    The autonomy loop must stay responsive: the tick budget cancels the
    in-flight reply and degrades to a stalled WAIT rather than blocking.
    """
    speaker = _SlowReplySpeaker(delay_seconds=5.0)
    layer = DeliberationLayer(speaker=speaker, tick_budget_seconds=0.2)
    decision = await asyncio.wait_for(
        layer.select(legal_actions=_FULL_LEGAL, world_state=_state()),
        timeout=2.0,  # the budget (0.2s) must fire well before this guard
    )
    assert decision.action is LegalAction.WAIT
    assert decision.fallback is True
    assert decision.stalled is True
    assert "budget" in decision.reasoning


@pytest.mark.asyncio
async def test_select_within_budget_succeeds() -> None:
    """A reply that lands inside the budget is a normal (non-stalled) decision."""
    speaker = _StubSpeaker(
        reply_text='{"action": "bekle", "reasoning": "sakin tick"}'
    )
    layer = DeliberationLayer(speaker=speaker, tick_budget_seconds=5.0)
    decision = await layer.select(
        legal_actions=_FULL_LEGAL, world_state=_state()
    )
    assert decision.action is LegalAction.WAIT
    assert decision.fallback is False
    assert decision.stalled is False
    assert decision.reasoning == "sakin tick"


@pytest.mark.asyncio
async def test_select_prose_only_reply_falls_back() -> None:
    speaker = _StubSpeaker(reply_text="Bence bekle ama JSON döndürmüyorum.")
    layer = DeliberationLayer(speaker=speaker)
    decision = await layer.select(
        legal_actions=_FULL_LEGAL, world_state=_state()
    )
    assert decision.action is LegalAction.WAIT
    assert decision.fallback is True
    assert "parse failed" in decision.reasoning


@pytest.mark.asyncio
async def test_select_unknown_action_falls_back() -> None:
    speaker = _StubSpeaker(
        reply_text='{"action": "wholly_invented", "reasoning": "x"}'
    )
    layer = DeliberationLayer(speaker=speaker)
    decision = await layer.select(
        legal_actions=_FULL_LEGAL, world_state=_state()
    )
    assert decision.action is LegalAction.WAIT
    assert decision.fallback is True


@pytest.mark.asyncio
async def test_select_action_outside_legal_set_falls_back() -> None:
    """Model picks IDEATE but legal set excludes it (creative off)."""
    speaker = _StubSpeaker(
        reply_text='{"action": "fikirleş", "reasoning": "yaratıcı moddayım"}'
    )
    layer = DeliberationLayer(speaker=speaker)
    decision = await layer.select(
        legal_actions=frozenset(LegalAction) - {LegalAction.IDEATE},
        world_state=_state(),
    )
    assert decision.action is LegalAction.WAIT
    assert decision.fallback is True


@pytest.mark.asyncio
async def test_select_malformed_json_falls_back() -> None:
    speaker = _StubSpeaker(
        reply_text='```json\n{"action": "bekle", "reasoning":\n```'  # malformed
    )
    layer = DeliberationLayer(speaker=speaker)
    decision = await layer.select(
        legal_actions=_FULL_LEGAL, world_state=_state()
    )
    assert decision.action is LegalAction.WAIT
    assert decision.fallback is True


@pytest.mark.asyncio
async def test_select_empty_reply_falls_back() -> None:
    speaker = _StubSpeaker(reply_text="")
    layer = DeliberationLayer(speaker=speaker)
    decision = await layer.select(
        legal_actions=_FULL_LEGAL, world_state=_state()
    )
    assert decision.action is LegalAction.WAIT
    assert decision.fallback is True


# ── User prompt rendering ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_user_prompt_includes_quota_summary_and_pause() -> None:
    speaker = _StubSpeaker(reply_text='{"action": "bekle", "reasoning": "ok"}')
    layer = DeliberationLayer(speaker=speaker)
    state = _state(
        pause_active=True,
        cli_quota={"claude-code": _quota("claude-code", 99.0)},
    )
    await layer.select(legal_actions=_FULL_LEGAL, world_state=state)
    user_msg = speaker.calls[0][1]["content"]
    assert "Pause flag: set" in user_msg
    assert "claude-code: 99% EXHAUSTED" in user_msg


@pytest.mark.asyncio
async def test_user_prompt_quota_no_signal_when_dict_empty() -> None:
    speaker = _StubSpeaker(reply_text='{"action": "bekle", "reasoning": "ok"}')
    layer = DeliberationLayer(speaker=speaker)
    await layer.select(
        legal_actions=_FULL_LEGAL, world_state=_state(cli_quota={})
    )
    user_msg = speaker.calls[0][1]["content"]
    assert "CLI quota: no signal" in user_msg


# ── Direct parser surface ────────────────────────────────────────────


def test_parse_decision_handles_extra_whitespace() -> None:
    reply = "\n```json\n  {\n    \"action\": \"bekle\",\n    \"reasoning\": \"r\"\n  }\n```\n"
    action, reasoning = _parse_decision(reply, _FULL_LEGAL)
    assert action is LegalAction.WAIT
    assert reasoning == "r"


def test_parse_decision_rejects_non_object() -> None:
    with pytest.raises(DeliberationParseError):
        _parse_decision('```json\n["bekle"]\n```', _FULL_LEGAL)


def test_parse_decision_rejects_missing_action() -> None:
    with pytest.raises(DeliberationParseError):
        _parse_decision('{"reasoning": "no action key"}', _FULL_LEGAL)


def test_parse_decision_reasoning_optional() -> None:
    """Missing ``reasoning`` is tolerated; falls back to empty string."""
    action, reasoning = _parse_decision(
        '{"action": "bekle"}', _FULL_LEGAL
    )
    assert action is LegalAction.WAIT
    assert reasoning == ""


# ── ADR-010 §2.2.6 — resume hint in the user prompt ──────────────────


@pytest.mark.asyncio
async def test_user_prompt_includes_resume_hint_when_present() -> None:
    speaker = _StubSpeaker(reply_text='{"action": "bekle", "reasoning": "ok"}')
    layer = DeliberationLayer(speaker=speaker)
    await layer.select(
        legal_actions=_FULL_LEGAL,
        world_state=_state(),
        resume_hint="Resuming after a restart — continue work on 'beta'.",
    )
    user_msg = speaker.calls[0][1]["content"]
    assert "Resuming after a restart" in user_msg
    assert "continue work on 'beta'" in user_msg
    # The hint precedes the current-state block.
    assert user_msg.index("Resuming") < user_msg.index("Current state")


@pytest.mark.asyncio
async def test_user_prompt_omits_resume_section_by_default() -> None:
    speaker = _StubSpeaker(reply_text='{"action": "bekle", "reasoning": "ok"}')
    layer = DeliberationLayer(speaker=speaker)
    await layer.select(legal_actions=_FULL_LEGAL, world_state=_state())
    user_msg = speaker.calls[0][1]["content"]
    assert "Resuming" not in user_msg
