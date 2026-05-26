"""Self Jr deliberative layer — model selects from the legal action set.

ADR-008 §4.3 hybrid control-loop, model half: the deterministic rules
layer (``LegalActionFilter``) has already narrowed the legal set; this
module asks Self Jr to **select** one action with a short reasoning
string. The model may NEVER widen the envelope — any selection outside
the legal set is treated as a parse failure and degrades to ``WAIT``
(deterministic fallback; the model is in the loop, not above it).

The prompt follows the Hexis ``heartbeat_agentic.md`` Orient → Check →
Decide template (verified via Hexis explorer-god report). The "rest"
mechanism mirrors Hexis: there is no special ``[REST]`` sentinel —
selecting ``bekle`` IS the rest. The system prompt asks the model to
prefer ``bekle`` when no productive action is needed.

Speaker unification (ADR-008 §12 risk note): both Talk (Self Jr ↔
operator) and Heartbeat (Self Jr ↔ orchestrator) connect through the
same :class:`~selffork_orchestrator.talk.speaker.Speaker` Protocol. The
round-loop's :class:`~selffork_orchestrator.runtime.mlx_server.MlxServerRuntime`
remains a spawn-owning client; Heartbeat is connect-only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from selffork_orchestrator.heartbeat.actions import LegalAction
from selffork_orchestrator.heartbeat.filter import WorldState
from selffork_orchestrator.talk.speaker import Speaker
from selffork_shared.errors import RuntimeUnhealthyError, SpeakerStalledError

__all__ = [
    "DELIBERATION_SYSTEM_PROMPT",
    "ActionDecision",
    "DeliberationLayer",
    "DeliberationParseError",
]


_log = logging.getLogger(__name__)


DELIBERATION_SYSTEM_PROMPT: Final[str] = """\
You are Self Jr, the operator's autonomous coding partner. You are at a \
Heartbeat tick — an outer-loop decision point where you decide what to do \
next (or whether to wait).

The orchestrator's deterministic rules layer has already filtered the set \
of legal actions for the current moment. You select EXACTLY ONE action \
from that set. You may NOT pick anything outside it; doing so cancels \
your decision and the system falls back to `bekle`.

Three-step protocol — follow it silently, then emit a single JSON block:

1. ORIENT — What is happening right now? (active workspace, pause state, \
quota state, concurrency.)
2. CHECK — Among the legal actions, which best serves the operator this \
moment?
3. DECIDE — Emit ONLY this JSON block (no prose outside it):

```json
{
  "action": "<one of the legal action values exactly>",
  "reasoning": "<one or two short sentences in Turkish>"
}
```

If no productive action is needed, prefer `bekle` and explain why in \
`reasoning`. Resting on a quiet tick is a first-class decision — not a \
failure.
"""


_JSON_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL
)
"""Match a fenced JSON block. The first capture group is the JSON body."""

_BARE_JSON_RE: Final[re.Pattern[str]] = re.compile(
    r"(\{[^{}]*\"action\"[^{}]*\})", re.DOTALL
)
"""Fallback: a bare JSON object containing an ``action`` key (no fences)."""


class DeliberationParseError(ValueError):
    """Raised when the model's reply cannot be parsed into an ActionDecision."""


@dataclass(frozen=True, slots=True)
class ActionDecision:
    """Self Jr's selection for one Heartbeat tick.

    Immutable record — written to the audit log + checkpoint exactly as
    selected (Faz E will wire the audit append).

    Attributes:
        action: The selected :class:`LegalAction`.
        reasoning: Model's short justification (1-2 sentences).
        selected_at: UTC timestamp the decision was made.
        fallback: ``True`` when the deliberation layer fell back to
            ``WAIT`` because the model was unhealthy or its response
            failed to parse. The audit log distinguishes "model chose
            wait" from "model unreachable → forced wait".
        stalled: ``True`` when the fallback was specifically caused by a
            slow/wedged model — the idle-token watchdog fired
            (:class:`SpeakerStalledError`) or the per-tick budget was
            exceeded (ADR-011 §3.4). Always implies ``fallback=True``;
            the extra flag lets the audit log + S-Train distinguish "model
            too slow on this tick" from "model unreachable / unparseable",
            and proves the autonomy loop never wedged on a slow tick.
    """

    action: LegalAction
    reasoning: str
    selected_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    fallback: bool = False
    stalled: bool = False


class DeliberationLayer:
    """Wraps a Speaker into a tick-scoped action selector.

    Construct once with the operator's Speaker (or a stub in tests);
    call :meth:`select` per tick. The layer is stateless except for the
    Speaker reference; concurrent ticks are safe but should not happen
    by design (eşzamanlılık limit = 1).
    """

    def __init__(
        self,
        *,
        speaker: Speaker,
        system_prompt: str = DELIBERATION_SYSTEM_PROMPT,
        fallback_action: LegalAction = LegalAction.WAIT,
        tick_budget_seconds: float | None = None,
    ) -> None:
        self._speaker = speaker
        self._system_prompt = system_prompt
        self._fallback_action = fallback_action
        # ADR-011 §3.4 per-tick wall-clock budget. ``None`` relies solely
        # on the Speaker's idle-token watchdog (a wedged model still
        # surfaces, just at the watchdog cadence); a positive value adds a
        # hard ceiling so a slow-but-producing model can't block the
        # autonomy loop for the full generation on a single tick.
        self._tick_budget_seconds = tick_budget_seconds

    async def select(
        self,
        *,
        legal_actions: frozenset[LegalAction],
        world_state: WorldState,
        resume_hint: str | None = None,
    ) -> ActionDecision:
        """Ask Self Jr to pick one action from ``legal_actions``.

        ``resume_hint`` (ADR-010 §2.2.6), when set, prepends one line of
        cross-tick continuity context to the user prompt — it never widens
        the legal set or alters the degradation rules below.

        Degradation rules (deterministic; never bypass-able by prompt):

        * Empty legal set → ``WAIT`` fallback (should never happen — the
          filter always returns at least ``WAIT``).
        * Speaker unreachable → ``WAIT`` fallback, ``fallback=True``.
        * Reply unparseable → ``WAIT`` fallback, ``fallback=True``.
        * Parsed action not in ``legal_actions`` → ``WAIT`` fallback,
          ``fallback=True`` (model tried to widen the envelope; rejected).
        """
        if not legal_actions:
            return ActionDecision(
                action=self._fallback_action,
                reasoning="legal set was empty (rules degenerate)",
                fallback=True,
            )

        user_prompt = self._render_user_prompt(
            legal_actions, world_state, resume_hint
        )
        messages: Sequence[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            if self._tick_budget_seconds is not None:
                reply = await asyncio.wait_for(
                    self._speaker.reply(messages),
                    timeout=self._tick_budget_seconds,
                )
            else:
                reply = await self._speaker.reply(messages)
        except SpeakerStalledError as exc:
            # Idle-token watchdog fired — the model produced no tokens for
            # the configured stall window (wedged / wrong runtime). Keep
            # the loop alive with an honest stalled WAIT.
            _log.warning(
                "heartbeat_deliberation_stalled",
                extra={"error": str(exc)},
            )
            return ActionDecision(
                action=self._fallback_action,
                reasoning="deliberation stalled (no tokens); defaulting to wait",
                fallback=True,
                stalled=True,
            )
        except TimeoutError as exc:
            # Per-tick wall-clock budget exceeded — the model was
            # producing but too slowly for an autonomy tick. Honest
            # stalled WAIT so the loop stays responsive.
            _log.warning(
                "heartbeat_deliberation_budget_exceeded",
                extra={
                    "budget_seconds": self._tick_budget_seconds,
                    "error": str(exc),
                },
            )
            return ActionDecision(
                action=self._fallback_action,
                reasoning=(
                    f"deliberation exceeded {self._tick_budget_seconds}s "
                    "tick budget; defaulting to wait"
                ),
                fallback=True,
                stalled=True,
            )
        except RuntimeUnhealthyError as exc:
            _log.warning(
                "heartbeat_deliberation_speaker_unhealthy",
                extra={"error": str(exc)},
            )
            return ActionDecision(
                action=self._fallback_action,
                reasoning="speaker unreachable; defaulting to wait",
                fallback=True,
            )

        try:
            action, reasoning = _parse_decision(reply, legal_actions)
        except DeliberationParseError as exc:
            _log.warning(
                "heartbeat_deliberation_parse_failed",
                extra={"error": str(exc), "reply": reply[:240]},
            )
            return ActionDecision(
                action=self._fallback_action,
                reasoning=f"parse failed ({exc}); defaulting to wait",
                fallback=True,
            )

        return ActionDecision(action=action, reasoning=reasoning)

    def _render_user_prompt(
        self,
        legal_actions: frozenset[LegalAction],
        state: WorldState,
        resume_hint: str | None = None,
    ) -> str:
        """Build the per-tick user message — small + structured."""
        legal_list = ", ".join(sorted(a.value for a in legal_actions))
        quota_summary = self._summarize_quota(state)
        creative = "ON" if state.creative_mode_enabled else "OFF"
        supervised = (
            "ON (every act → Telegram approval)"
            if state.supervised_mode
            else "OFF"
        )
        workspace = state.last_active_workspace or "—"
        concurrency = (
            f"{state.active_concurrent_sessions} / "
            f"{state.max_concurrent_sessions}"
        )
        prefix = (
            f"== Resuming after a restart ==\n{resume_hint}\n\n"
            if resume_hint
            else ""
        )
        return (
            prefix
            + "== Current state ==\n"
            f"- Active workspace (last operator activity): {workspace}\n"
            f"- Pause flag: {'set' if state.pause_active else 'clear'}\n"
            f"- Active concurrent sessions: {concurrency}\n"
            f"- Creative mode: {creative}\n"
            f"- Supervised (Denetimli) preset: {supervised}\n"
            f"- CLI quota: {quota_summary}\n"
            "\n"
            f"== Legal actions ==\n{legal_list}\n"
            "\n"
            "Select one action and reply with ONLY the JSON block."
        )

    def _summarize_quota(self, state: WorldState) -> str:
        if not state.cli_quota:
            return "no signal"
        rows: list[str] = []
        for cli_id, snap in state.cli_quota.items():
            if snap is None:
                rows.append(f"{cli_id}: ?")
                continue
            exhausted = snap.is_exhausted(state.quota_exhaustion_threshold_pct)
            if not snap.windows:
                rows.append(f"{cli_id}: no windows")
                continue
            highest_pct = max(w.used_pct for w in snap.windows.values())
            status = "EXHAUSTED" if exhausted else "ok"
            rows.append(f"{cli_id}: {highest_pct:.0f}% {status}")
        return "; ".join(rows)


# ── parsing internals ───────────────────────────────────────────────


def _parse_decision(
    reply: str, legal_actions: frozenset[LegalAction]
) -> tuple[LegalAction, str]:
    """Extract ``(action, reasoning)`` from a model reply.

    Tries fenced JSON first, then bare JSON. Raises
    :class:`DeliberationParseError` for any failure (caller converts to
    the fallback decision).
    """
    payload = _extract_json_payload(reply)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        msg = f"JSON decode failed: {exc}"
        raise DeliberationParseError(msg) from exc

    if not isinstance(data, dict):
        msg = f"expected JSON object, got {type(data).__name__}"
        raise DeliberationParseError(msg)

    raw_action = data.get("action")
    if not isinstance(raw_action, str):
        msg = "missing or non-string 'action' field"
        raise DeliberationParseError(msg)
    try:
        action = LegalAction(raw_action)
    except ValueError as exc:
        msg = f"unknown action value {raw_action!r}"
        raise DeliberationParseError(msg) from exc

    if action not in legal_actions:
        msg = (
            f"action {action.value!r} is not in the legal set "
            f"({sorted(a.value for a in legal_actions)})"
        )
        raise DeliberationParseError(msg)

    reasoning_raw = data.get("reasoning", "")
    reasoning = reasoning_raw if isinstance(reasoning_raw, str) else ""
    return action, reasoning.strip()


def _extract_json_payload(reply: str) -> str:
    """Find the JSON body in a model reply (fenced or bare)."""
    if not reply.strip():
        msg = "empty reply"
        raise DeliberationParseError(msg)

    fenced = _JSON_BLOCK_RE.search(reply)
    if fenced is not None:
        return fenced.group(1)

    bare = _BARE_JSON_RE.search(reply)
    if bare is not None:
        return bare.group(1)

    msg = "no JSON object found"
    raise DeliberationParseError(msg)
