"""Heartbeat scheduler daemon (S-Auto Faz A).

ADR-008 §3 outer-loop scaffold — the ``perceive → decide → act → record``
tick that sits above the existing round-loop. Faz A shipped the daemon
shell (lifecycle start/stop, tick loop, deterministic reactive gates —
pause flag + active-hours window — and an event queue); Faz B-E filled
in the rest. ``_one_tick`` now runs the full pipeline: legal-action
filter (Faz B) → deliberative selector (Faz C, optional) → executor
(Faz D, optional) → AIR detector + audit/checkpoint record (Faz E).
Deliberation/executor/audit surfaces are independently optional, so an
unwired daemon degrades to pure observe mode instead of failing.

Pattern parity:
* lifecycle wrapper + :class:`StrEnum` state machine mirror
  :class:`selffork_orchestrator.snappers.codexbar_server.CodexBarServer`;
* tick-task body + cancellation-aware shutdown mirror
  :mod:`selffork_orchestrator.telegram.expire_loop`;
* active-hours parsing mirrors Hexis ``worker_service.py:143-190``
  (overnight wrap, fail-OPEN on parse error).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import zoneinfo
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from selffork_orchestrator.heartbeat.actions import LegalAction
from selffork_orchestrator.heartbeat.air import AIRAlert, AIRDetector
from selffork_orchestrator.heartbeat.audit import (
    AuditWriter,
    build_audit_entry,
)
from selffork_orchestrator.heartbeat.checkpoint import (
    Checkpoint,
    CheckpointWriter,
)
from selffork_orchestrator.heartbeat.config import (
    HeartbeatConfig,
    build_default_heartbeat_config,
)
from selffork_orchestrator.heartbeat.deliberation import (
    ActionDecision,
    DeliberationLayer,
)
from selffork_orchestrator.heartbeat.executor import (
    ActionExecutor,
    ActionResult,
)
from selffork_orchestrator.heartbeat.filter import (
    LegalActionFilter,
    WorldState,
    WorldStateBuilder,
)
from selffork_orchestrator.telegram.bridge import (
    TelegramBridge,
    TelegramMessage,
)
from selffork_orchestrator.telegram.inbound_router import PauseSignal

if TYPE_CHECKING:
    from selffork_mind.reflection.auto_dream import (
        AutoDreamReport,
        AutoDreamRunner,
    )

__all__ = [
    "HeartbeatEvent",
    "HeartbeatScheduler",
    "HeartbeatState",
    "compute_within_active_hours",
]

_log = logging.getLogger(__name__)

_INACTIVE_SLEEP_MULTIPLIER: Final[int] = 10
"""Multiplier applied to ``tick_seconds`` when outside the active window.

Hexis ``worker_service.py:112`` pattern: off-hours sleeps stay
shutdown-responsive but burn near-zero CPU.
"""


class HeartbeatState(StrEnum):
    """Lifecycle states for :class:`HeartbeatScheduler`.

    ``INACTIVE → STARTING → RUNNING → STOPPING → STOPPED`` is the happy
    path; ``DISABLED`` (config opt-out) and ``FAILED`` (unhandled boot
    error) are absorbing terminal states.
    """

    INACTIVE = "inactive"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    DISABLED = "disabled"
    FAILED = "failed"


class HeartbeatEvent(StrEnum):
    """Source-tagged event kinds the daemon drains from its queue.

    Faz D wires real producers (kanban router, talk router, telegram
    inbound router, ``[SELFFORK:DONE]`` sentinel). Faz A only defines
    the surface so unit tests can inject events directly through
    :meth:`HeartbeatScheduler.submit_event`.
    """

    KANBAN_CHANGED = "kanban.changed"
    SESSION_DONE = "session.done"
    OPERATOR_MESSAGE = "operator.message"
    TELEGRAM_INBOUND = "telegram.inbound"
    RECONCILIATION = "reconciliation"


class HeartbeatScheduler:
    """Async daemon implementing the outer perceive→decide→act→record loop.

    One instance per orchestrator process. Construct sync (no side
    effects); :meth:`start` spawns the asyncio task; :meth:`stop`
    cancels and awaits clean teardown. Both methods are idempotent —
    calling either twice is safe.

    The tick body perceives via the deterministic reactive layer first
    (pause flag + active-hours gate; ADR-008 §4.3 "rules constrain,
    model selects") before any model call. ``decide``/``act``/``record``
    are stubs in Faz A and filled by Faz B/C/D/E.
    """

    def __init__(
        self,
        *,
        config: HeartbeatConfig | None = None,
        pause_signal: PauseSignal | None = None,
        legal_action_filter: LegalActionFilter | None = None,
        world_state_builder: WorldStateBuilder | None = None,
        deliberation_layer: DeliberationLayer | None = None,
        action_executor: ActionExecutor | None = None,
        audit_writer: AuditWriter | None = None,
        checkpoint_writer: CheckpointWriter | None = None,
        air_detector: AIRDetector | None = None,
        emergency_telegram_bridge: TelegramBridge | None = None,
        auto_dream_runner: AutoDreamRunner | None = None,
    ) -> None:
        self._config = config or build_default_heartbeat_config()
        self._pause = pause_signal or PauseSignal()
        self._filter = legal_action_filter or LegalActionFilter()
        self._world_state_builder = (
            world_state_builder
            if world_state_builder is not None
            else WorldStateBuilder(
                config=self._config,
                pause_signal=self._pause,
                within_active_hours_probe=lambda: compute_within_active_hours(
                    self._config.active_hours, self._config.timezone
                ),
            )
        )
        self._deliberation = deliberation_layer
        self._executor = action_executor
        self._audit_writer = audit_writer
        self._checkpoint_writer = checkpoint_writer
        self._air_detector = air_detector
        self._emergency_bridge = emergency_telegram_bridge
        # ADR-009 §4 — optional threshold-gated GLOBAL-pool reflection.
        # Wired the same way as deliberation/executor/audit: ``None`` keeps
        # the daemon in pure observe mode; a wired runner self-gates so the
        # per-tick call is cheap until all four dream thresholds hold.
        self._auto_dream_runner = auto_dream_runner
        self._last_auto_dream_report: AutoDreamReport | None = None
        self._state = (
            HeartbeatState.DISABLED
            if not self._config.enabled
            else HeartbeatState.INACTIVE
        )
        self._task: asyncio.Task[None] | None = None
        self._event_queue: asyncio.Queue[HeartbeatEvent] = asyncio.Queue()
        self._last_reconciliation_ts: float = 0.0
        self._tick_count: int = 0
        self._last_legal_actions: frozenset[LegalAction] | None = None
        self._last_action_decision: ActionDecision | None = None
        self._last_action_result: ActionResult | None = None
        self._last_air_alert: AIRAlert | None = None
        self._self_stop_requested: bool = False
        # ADR-010 §2.2.6 cross-tick resume. ``start()`` reads the last
        # checkpoint into ``_resumed_from`` (None on a cold first boot); the
        # first productive deliberation tick consumes it as a one-shot
        # resume hint (``_resume_consumed`` guards the one-shot).
        self._resumed_from: Checkpoint | None = None
        self._resume_consumed: bool = False

    # ── public API ────────────────────────────────────────────────────

    @property
    def state(self) -> HeartbeatState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state is HeartbeatState.RUNNING

    @property
    def config(self) -> HeartbeatConfig:
        return self._config

    @property
    def tick_count(self) -> int:
        """Number of decide-stage ticks since the last :meth:`start`.

        Excludes pause-skipped and active-hours-skipped ticks (those
        short-circuit before decide). Exposed for tests + future Faz E
        audit metrics.
        """
        return self._tick_count

    @property
    def last_legal_actions(self) -> frozenset[LegalAction] | None:
        """The legal-action set computed on the most recent decide tick.

        ``None`` before any decide tick has executed (daemon just booted
        or all ticks have been short-circuited by pause / active-hours).
        Exposed for tests + ``GET /api/heartbeat/state`` (Faz H surface).
        """
        return self._last_legal_actions

    @property
    def last_action_decision(self) -> ActionDecision | None:
        """The most recent action the deliberative layer selected.

        ``None`` when no deliberation layer is wired or no decide tick
        has executed yet. ``fallback=True`` on the decision means the
        model was unhealthy / output unparseable and the deterministic
        fallback (``WAIT``) was used.
        """
        return self._last_action_decision

    @property
    def last_action_result(self) -> ActionResult | None:
        """The most recent :class:`ActionResult` from the executor.

        ``None`` when no executor is wired or no decide tick has
        executed yet. ``outcome`` reveals whether the side effect was
        committed (``executed``), recorded for later (``deferred``),
        not yet configured (``skipped``), or attempted-and-failed
        (``failed``).
        """
        return self._last_action_result

    @property
    def last_air_alert(self) -> AIRAlert | None:
        """The most recent :class:`AIRAlert` raised by the detector.

        ``None`` until AIR has fired. When set, ``severity`` reveals
        urgency and ``recommended_recovery`` carries the operator-facing
        recovery hint. The daemon also self-stops on any AIR alert so
        this is also the post-mortem record.
        """
        return self._last_air_alert

    @property
    def resumed_from(self) -> Checkpoint | None:
        """The checkpoint :meth:`start` resumed from, or ``None``.

        Set at boot from the on-disk checkpoint (ADR-010 §2.2.6) so the
        dashboard / tests can see what the daemon picked up. The one-shot
        resume *hint* derived from it is delivered to the first productive
        deliberation tick and then cleared; this property keeps the raw
        boot value for introspection.
        """
        return self._resumed_from

    @property
    def last_auto_dream_report(self) -> AutoDreamReport | None:
        """The most recent Auto Dream run (ADR-009 §4), or ``None``.

        ``None`` when no runner is wired or the gate has never opened (the
        common case — a dream needs >=24h + >=5 sessions + not rate-limited
        + idle). When set, ``reflection.reflections_written`` and
        ``duration_seconds`` summarise the last GLOBAL-pool consolidation.
        """
        return self._last_auto_dream_report

    def submit_event(self, event: HeartbeatEvent) -> None:
        """Non-blocking event submission — the event-driven hot path.

        Faz D producers call this to wake the daemon between
        reconciliation ticks. Safe to call before :meth:`start` —
        events queue until the daemon drains them on first tick.
        """
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:  # pragma: no cover — unbounded queue
            _log.warning("heartbeat_event_queue_full", extra={"event": event.value})

    async def start(self) -> None:
        """Boot the daemon if enabled; no-op when disabled or already running.

        Audit fix #1 (audit-god 2026-05-23 MAJOR): explicitly reset
        ``_self_stop_requested`` so an in-process restart after a
        cooperative ``SELF_STOP`` (or AIR alert) actually spawns a
        working tick loop rather than a zombie task that exits on its
        first iteration.
        """
        if self._state is HeartbeatState.DISABLED:
            _log.info("heartbeat_skipped_disabled")
            return
        if self._state in (HeartbeatState.STARTING, HeartbeatState.RUNNING):
            return
        self._self_stop_requested = False
        self._resume_consumed = False
        self._resumed_from = self._read_resume_checkpoint()
        self._state = HeartbeatState.STARTING
        self._tick_count = 0
        self._last_reconciliation_ts = time.monotonic()
        self._task = asyncio.create_task(
            self._tick_loop(), name="heartbeat-daemon"
        )
        self._state = HeartbeatState.RUNNING
        _log.info(
            "heartbeat_started",
            extra={
                "tick_seconds": self._config.tick_seconds,
                "reconciliation_seconds": self._config.reconciliation_seconds,
                "active_hours": self._config.active_hours,
                "timezone": self._config.timezone,
                "max_concurrency": self._config.max_concurrency,
            },
        )

    async def stop(self) -> None:
        """Cancel the tick task and await clean teardown.

        Idempotent — safe on a disabled / already-stopped instance.
        Preserves the ``DISABLED`` terminal state (so the dashboard
        lifespan teardown can still call this unconditionally).
        """
        if self._task is None:
            if self._state is not HeartbeatState.DISABLED:
                self._state = HeartbeatState.STOPPED
            return
        if self._state in (HeartbeatState.STOPPED, HeartbeatState.STOPPING):
            return
        self._state = HeartbeatState.STOPPING
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task
        self._task = None
        self._state = HeartbeatState.STOPPED
        _log.info(
            "heartbeat_stopped", extra={"tick_count": self._tick_count}
        )

    # ── internals ─────────────────────────────────────────────────────

    async def _tick_loop(self) -> None:
        """Main daemon body — runs until cancelled or self-stop.

        Cooperative shutdown: when an ``SELF_STOP`` action lands in
        ``last_action_result.outcome == "executed"`` the next iteration
        exits cleanly and the daemon transitions to
        :attr:`HeartbeatState.STOPPED`. External :meth:`stop` still
        cancels the task directly + remains idempotent.
        """
        try:
            while not self._self_stop_requested:
                await self._one_tick()
        finally:
            if self._self_stop_requested:
                self._state = HeartbeatState.STOPPED
                self._task = None

    async def _one_tick(self) -> None:
        """Execute one perceive→decide→act→record cycle.

        * **perceive** — pause flag + active-hours gate, then the full
          deterministic world snapshot via ``WorldStateBuilder``.
        * **decide** — Faz B legal-action filter, then the optional
          Faz C deliberation layer selects an action (observe-only
          when no deliberation is wired).
        * **act** — the optional Faz D executor runs the decision
          (honours ``SELF_STOP`` cooperatively).
        * **record** — Faz E AIR detector check, then audit append +
          checkpoint refresh (each independently optional).
        """
        # PERCEIVE — reactive gates first (ADR-008 §4.3, Lock #3).
        if self._pause.is_set():
            await asyncio.sleep(self._config.tick_seconds)
            return
        if not self._within_active_hours():
            await asyncio.sleep(
                self._config.tick_seconds * _INACTIVE_SLEEP_MULTIPLIER
            )
            return

        # Drain an event or wait for the reconciliation timeout. The
        # event/timer split is ADR-008 §4.2: events drive the hot path,
        # the timer is the safety net.
        event = await self._await_event_or_reconciliation()

        # PERCEIVE (full) — build the deterministic world snapshot.
        world_state = await self._world_state_builder.build()

        # DECIDE — Faz B (filter) narrows the set; Faz C (deliberation)
        # asks Self Jr to select. The deliberation layer is optional;
        # without it we only record the legal set (Faz B behaviour).
        legal_actions = self._filter.legal_actions(world_state)
        self._last_legal_actions = legal_actions

        if self._deliberation is not None:
            resume_hint = self._peek_resume_hint()
            self._last_action_decision = await self._deliberation.select(
                legal_actions=legal_actions,
                world_state=world_state,
                resume_hint=resume_hint,
            )
            # Consume the one-shot resume hint only once it reached a real
            # decision — a fallback tick (stalled / unparseable; ADR-011)
            # never wove it into the prompt, so keep it pending for the next
            # tick. A cold or gate-rejected boot has ``_resumed_from``/hint
            # None and is simply marked spent the first time deliberation runs.
            if not self._last_action_decision.fallback:
                self._resume_consumed = True

        # ACT (Faz D) — only invoked when both deliberation + executor
        # are wired. Without one or the other the daemon stays in a
        # pure observe mode (Faz A/B/C behaviour).
        if (
            self._executor is not None
            and self._last_action_decision is not None
        ):
            self._last_action_result = await self._executor.execute(
                self._last_action_decision, world_state
            )
            if (
                self._last_action_result.outcome == "executed"
                and self._last_action_result.action is LegalAction.SELF_STOP
            ):
                # Cooperative shutdown — the tick loop exits cleanly
                # on the next iteration; ``stop()`` may still be
                # called externally and remains idempotent.
                self._self_stop_requested = True

        # AIR (Faz E researcher gap) — detect panic/cover-up/sustained
        # failure signals AFTER the executor result is in hand. A live
        # alert sets ``self_stop_requested`` and pushes a critical
        # Telegram message (when wired).
        air_alert: AIRAlert | None = None
        if self._air_detector is not None:
            air_alert = self._air_detector.check(
                decision=self._last_action_decision,
                result=self._last_action_result,
            )
            if air_alert is not None:
                self._last_air_alert = air_alert
                self._self_stop_requested = True
                await self._dispatch_air_alert(air_alert, world_state)

        # RECORD (Faz E) — append the audit entry + refresh the
        # checkpoint. Both surfaces are independently optional so the
        # daemon stays useful when only one is wired.
        self._tick_count += 1
        if self._audit_writer is not None:
            entry = build_audit_entry(
                tick=self._tick_count,
                trigger=event.value,
                world_state=world_state,
                legal_actions=frozenset(
                    a.value for a in legal_actions
                ),
                decision=self._last_action_decision,
                result=self._last_action_result,
                air_alert=(
                    air_alert.severity if air_alert is not None else None
                ),
            )
            try:
                self._audit_writer.write(entry)
            except OSError:
                _log.exception("heartbeat_audit_write_failed")
        if self._checkpoint_writer is not None:
            self._update_checkpoint(world_state)

        _log.debug(
            "heartbeat_tick",
            extra={
                "tick": self._tick_count,
                "trigger": event.value,
                "legal_actions": sorted(a.value for a in legal_actions),
                "selected": (
                    self._last_action_decision.action.value
                    if self._last_action_decision is not None
                    else None
                ),
                "fallback": (
                    self._last_action_decision.fallback
                    if self._last_action_decision is not None
                    else None
                ),
                "stalled": (
                    self._last_action_decision.stalled
                    if self._last_action_decision is not None
                    else None
                ),
                "outcome": (
                    self._last_action_result.outcome
                    if self._last_action_result is not None
                    else None
                ),
                "air_severity": (
                    air_alert.severity if air_alert is not None else None
                ),
            },
        )

        # REFLECT (ADR-009 §4) — optional threshold-gated Auto Dream over
        # the GLOBAL pool. Runs last (after record) and only when a runner
        # is wired and the daemon isn't already halting. Like every other
        # optional surface it is a no-op when unwired; the runner's own gate
        # keeps the per-tick call cheap, and it is fail-soft so a reflection
        # error never kills the outer loop.
        if self._auto_dream_runner is not None and not self._self_stop_requested:
            await self._maybe_auto_dream(self._auto_dream_runner, world_state)

    async def _maybe_auto_dream(
        self, runner: AutoDreamRunner, world_state: WorldState
    ) -> None:
        """Evaluate + (rarely) run the Auto Dream gate for one tick.

        ADR-009 §4's pseudocode reads ``world_state.rate_limited`` and
        ``world_state.last_activity_at``; the shipped
        :class:`~selffork_orchestrator.heartbeat.filter.WorldState` exposes
        neither, so we derive both from the fields it does carry:

        * ``rate_limited`` — true when every tracked CLI's quota is
          exhausted (``not any_cli_has_quota()``); the ADR-008 quota signal.
        * idle — approximated from the live inner-loop session count. A busy
          tick stamps ``now`` as the last activity so the runner's idle
          sub-gate blocks; an idle tick passes ``None`` to disable that
          sub-gate (the other three thresholds still apply).

        GLOBAL pool only (``project_slug=None``) per ADR-009 §3 T5.
        """
        now = datetime.now(UTC)
        rate_limited = not world_state.any_cli_has_quota()
        busy = world_state.active_concurrent_sessions > 0
        try:
            report = await runner.maybe_run(
                now=now,
                rate_limited=rate_limited,
                last_activity_at=now if busy else None,
                project_slug=None,
            )
        except Exception:
            _log.exception("heartbeat_auto_dream_failed")
            return
        if report is None:
            return
        self._last_auto_dream_report = report
        _log.info(
            "heartbeat_auto_dream_ran",
            extra={
                "duration_seconds": report.duration_seconds,
                "reflections_written": report.reflection.reflections_written,
            },
        )

    async def _dispatch_air_alert(
        self, alert: AIRAlert, state: WorldState
    ) -> None:
        """Push a ``crit`` Telegram message when an emergency bridge is wired."""
        if self._emergency_bridge is None:
            _log.warning(
                "heartbeat_air_alert_no_bridge",
                extra={
                    "severity": alert.severity,
                    "reason": alert.reason,
                },
            )
            return
        text = (
            f"🚨 SelfFork Heartbeat AIR Alert ({alert.severity.upper()})\n\n"
            f"Reason: {alert.reason}\n"
            f"Consecutive failures: {alert.consecutive_failures}\n\n"
            "Recovery hint:\n"
            f"{alert.recommended_recovery}\n\n"
            "Daemon has self-stopped. Inspect "
            "~/.selffork/heartbeat/audit.jsonl."
        )
        message = TelegramMessage(
            level="crit",
            text=text,
            session_id="heartbeat-air",
            project_slug=state.last_active_workspace,
        )
        try:
            await self._emergency_bridge.notify(message)
        except Exception:
            _log.exception("heartbeat_air_alert_dispatch_failed")

    def _read_resume_checkpoint(self) -> Checkpoint | None:
        """Load the last on-disk checkpoint for a cross-tick resume.

        ADR-010 §2.2.6: the checkpoint the daemon writes every tick is only
        half the loop — without reading it on boot the daemon has no memory
        of interrupted work across a restart. Returns ``None`` when no
        writer is wired or no (valid) checkpoint exists (a cold boot).
        """
        if self._checkpoint_writer is None:
            return None
        checkpoint = self._checkpoint_writer.read()
        if checkpoint is not None:
            _log.info(
                "heartbeat_resumed_from_checkpoint",
                extra={
                    "step": checkpoint.step,
                    "next_action": checkpoint.next_action,
                    "workspace": checkpoint.workspace,
                    "progress": checkpoint.progress,
                },
            )
        return checkpoint

    def _peek_resume_hint(self) -> str | None:
        """The pending one-shot resume hint, WITHOUT consuming it.

        Returns the hint derived from the boot checkpoint until it has been
        *delivered* to a real (non-fallback) deliberation tick; ``_one_tick``
        flips ``_resume_consumed`` only after such a delivery, so a degraded
        first tick (stalled / unparseable → fallback ``WAIT``; ADR-011) keeps
        the hint pending for the next tick instead of silently dropping it
        (ADR-010 §2.2.6). ``None`` when the boot was cold, the hint was
        already delivered, or the resumed checkpoint isn't worth resuming (a
        quiet ``bekle`` tick or a deliberate ``kendini_durdur`` halt — see
        :func:`_build_resume_hint`).
        """
        if self._resumed_from is None or self._resume_consumed:
            return None
        return _build_resume_hint(self._resumed_from)

    def _update_checkpoint(self, world_state: WorldState) -> None:
        """Write the latest ``{step, progress, next_action, workspace}`` snapshot."""
        if self._checkpoint_writer is None:
            return
        if self._self_stop_requested:
            step = "halted"
            next_action = LegalAction.SELF_STOP.value
        elif self._last_action_result is not None:
            step = "act"
            next_action = (
                self._last_action_decision.action.value
                if self._last_action_decision is not None
                else LegalAction.WAIT.value
            )
        else:
            step = "perceive"
            next_action = LegalAction.WAIT.value
        failure_count = (
            self._air_detector.consecutive_failures
            if self._air_detector is not None
            else 0
        )
        progress = (
            f"tick={self._tick_count} "
            f"workspace={world_state.last_active_workspace or '-'} "
            f"failures={failure_count}"
        )
        checkpoint = Checkpoint(
            step=step,
            progress=progress,
            next_action=next_action,
            workspace=world_state.last_active_workspace,
        )
        try:
            self._checkpoint_writer.write(checkpoint)
        except OSError:
            _log.exception("heartbeat_checkpoint_write_failed")

    async def _await_event_or_reconciliation(self) -> HeartbeatEvent:
        """Block on the event queue with a reconciliation-timer fallback.

        Returns the first event that arrives, or
        :attr:`HeartbeatEvent.RECONCILIATION` if the safety-net interval
        elapses with no events. Resets the safety-net clock on every
        return so the timer stays a pure fallback rather than a
        competing fast trigger.
        """
        now = time.monotonic()
        elapsed = now - self._last_reconciliation_ts
        timeout = max(0.0, self._config.reconciliation_seconds - elapsed)
        try:
            event = await asyncio.wait_for(
                self._event_queue.get(), timeout=timeout
            )
        except TimeoutError:
            self._last_reconciliation_ts = time.monotonic()
            return HeartbeatEvent.RECONCILIATION
        else:
            self._last_reconciliation_ts = time.monotonic()
            return event

    def _within_active_hours(self) -> bool:
        """Deterministic active-window check.

        Thin wrapper over the module-level
        :func:`compute_within_active_hours` so the WorldStateBuilder
        and the scheduler's perceive stage share a single
        implementation.
        """
        return compute_within_active_hours(
            self._config.active_hours, self._config.timezone
        )


_RESUME_EXCLUDED_ACTIONS: Final[frozenset[str]] = frozenset(
    {LegalAction.WAIT.value, LegalAction.SELF_STOP.value},
)
"""Checkpoint ``next_action`` values that are NOT worth auto-resuming.

A quiet ``bekle`` tick or a deliberate ``kendini_durdur`` halt is not
interrupted work; surfacing a "continue this" hint for them would push the
daemon to re-engage something it intentionally left alone.
"""


def _build_resume_hint(checkpoint: Checkpoint) -> str | None:
    """Render a one-line resume hint from a boot checkpoint, or ``None``.

    ADR-010 §2.2.6 "the next tick continues": only a checkpoint captured
    mid-action (``step == "act"``) whose intended ``next_action`` was
    productive surfaces a hint; a halt or a quiet wait does not. The hint is
    continuity context for the deliberation prompt, not a command — the
    model still decides whether the work still serves the operator.
    """
    if checkpoint.step != "act":
        return None
    if checkpoint.next_action in _RESUME_EXCLUDED_ACTIONS:
        return None
    workspace = checkpoint.workspace or "—"
    return (
        f"Resuming after a restart — your last recorded tick intended "
        f"'{checkpoint.next_action}' on workspace '{workspace}'. Continue "
        "that work if it still serves the operator, or reassess."
    )


def compute_within_active_hours(active_hours: str, timezone: str) -> bool:
    """Public, sync helper for the active-hours gate (Hexis pattern).

    Parses ``"HH:MM-HH:MM"`` 24h. Overnight ranges wrap midnight; parse
    failure fails OPEN (returns ``True``) so a config typo never
    silently silences the daemon.

    Exposed so :class:`WorldStateBuilder` can wire the same probe
    without reaching into a :class:`HeartbeatScheduler` instance.
    """
    spec = active_hours.strip()
    if not spec or "-" not in spec:
        return True
    try:
        start_raw, end_raw = spec.split("-", 1)
        start_minutes = _parse_hhmm(start_raw)
        end_minutes = _parse_hhmm(end_raw)
    except ValueError:
        _log.warning(
            "heartbeat_active_hours_parse_failed", extra={"spec": spec}
        )
        return True

    try:
        tz = zoneinfo.ZoneInfo(timezone)
    except zoneinfo.ZoneInfoNotFoundError:  # pragma: no cover
        tz = zoneinfo.ZoneInfo("UTC")
    now_local = datetime.now(tz=tz)
    current_minutes = now_local.hour * 60 + now_local.minute

    if start_minutes == end_minutes:
        return True
    if start_minutes < end_minutes:
        return start_minutes <= current_minutes < end_minutes
    # Overnight: window wraps midnight.
    return current_minutes >= start_minutes or current_minutes < end_minutes


def _parse_hhmm(value: str) -> int:
    """Parse ``"HH:MM"`` into minutes-since-midnight; ``"24:00"`` = 1440."""
    value = value.strip()
    parts = value.split(":")
    if len(parts) != 2:
        msg = f"invalid HH:MM value: {value!r}"
        raise ValueError(msg)
    hours = int(parts[0])
    minutes = int(parts[1])
    if hours == 24 and minutes == 0:
        return 24 * 60
    if not (0 <= hours <= 23) or not (0 <= minutes <= 59):
        msg = f"out-of-range time: {value!r}"
        raise ValueError(msg)
    return hours * 60 + minutes
