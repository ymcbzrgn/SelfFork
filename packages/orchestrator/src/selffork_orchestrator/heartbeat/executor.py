"""Action executor — implement ADR-008 §4.4 closed vocabulary (S-Auto Faz D).

Faz D turns an :class:`ActionDecision` into a real-world side effect (or
records "deferred" / "skipped" when the dependency is not yet wired).
The executor is **callable-injected**: each external side effect
(subprocess spawn, Telegram notify, kanban card creation) is an
optional callable. When ``None``, the corresponding action lands in
``skipped`` with a clear reason — the daemon stays observable.

Per-action behaviour (ADR-008 §4.4):

* ``WAIT`` / ``SELF_STOP`` — pure (no external dep). ``SELF_STOP``
  flags the scheduler to exit; ``WAIT`` records a quiet tick.
* ``OPERATOR_ASK`` — :class:`TelegramBridge.notify` reuse (S3 outbound).
* ``TASK_START`` — :class:`TaskStarter` callable; the dashboard wires
  it to ``selffork run --project <slug>`` subprocess fan-out.
* ``KANBAN_SUGGEST`` — :class:`KanbanCardCreator` callable; appends a
  card to the active project's kanban.
* ``SESSION_RESUME`` / ``IDEATE`` — record intent only in Faz D; wired
  by later sprints (resume daemon, Faz F Yaratma mode).
* ``CLI_SELECT`` — :class:`CliSelector` callable picks a CLI via the S6
  router (ADR-006 §4.6 — override → quota → affinity). ``None`` selector
  ⇒ ``skipped``; fleet-wide quota exhaustion ⇒ ``skipped``.

Every action returns an :class:`ActionResult` with an ``outcome`` of
``executed``, ``deferred``, ``skipped`` or ``failed`` so the audit
layer (Faz E) and the dashboard (Faz H) can render the right state.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Literal, assert_never

from selffork_orchestrator.heartbeat.actions import LegalAction
from selffork_orchestrator.heartbeat.creative import IdeationManager
from selffork_orchestrator.heartbeat.deliberation import ActionDecision
from selffork_orchestrator.heartbeat.filter import WorldState
from selffork_orchestrator.telegram.bridge import (
    TelegramBridge,
    TelegramMessage,
)

__all__ = [
    "ActionExecutor",
    "ActionOutcome",
    "ActionResult",
    "BodyDriverOutcome",
    "BodyReviewDriver",
    "BodyUseDriver",
    "CliSelectionOutcome",
    "CliSelector",
    "KanbanCardCreator",
    "TaskStarter",
]


_log = logging.getLogger(__name__)


_HEARTBEAT_TELEGRAM_SESSION_ID: Final[str] = "heartbeat"
"""Synthetic ``session_id`` used for Heartbeat-origin Telegram messages.

Heartbeat ticks are not :class:`~selffork_orchestrator.lifecycle.session.Session`
instances; the outbound bridge ties messages to sessions for replay /
audit correlation, so the daemon uses a fixed token the dashboard can
recognise and skip in session-scoped views.
"""


ActionOutcome = Literal["executed", "deferred", "skipped", "failed"]


TaskStarter = Callable[[str, str], Awaitable[int | None]]
"""``async (project_slug, prd_text) → process_pid | None``.

The dashboard wires this to the same ``selffork run --project <slug>``
fan-out the ``POST /api/sessions/run`` endpoint uses
(``dashboard/server.py:878-883`` pattern). Returning ``None`` signals
spawn failure; an :class:`Exception` is caught + reported as
``outcome="failed"``.
"""


KanbanCardCreator = Callable[[str, str, str], Awaitable[str]]
"""``async (project_slug, title, body) → new_card_id``.

Wired by the dashboard to
:meth:`selffork_orchestrator.projects.store.ProjectStore.load_board` +
``add_card`` + ``save_board`` (ADR-006 §5.4 Kanban data path).
"""


@dataclass(frozen=True, slots=True)
class CliSelectionOutcome:
    """Result of a CLI-router ``select_cli`` call (executor-facing).

    Kept deliberately small + defined here (not imported from the
    orchestrator router) so :mod:`heartbeat` never imports the router —
    the router imports :mod:`heartbeat.filter`, so the dependency stays
    one-way. ``cli is None`` means no eligible CLI (fleet-wide quota
    exhaustion); the handler then surfaces ``skipped``.
    """

    cli: str | None
    reasoning: str
    metadata: dict[str, object] = field(default_factory=dict)


CliSelector = Callable[["WorldState"], Awaitable[CliSelectionOutcome]]
"""``async (world_state) → CliSelectionOutcome`` (S6 CLI router).

The dashboard wires this to the ADR-006 §4.6 router: it reads
``world_state.last_active_workspace`` and returns the chosen CLI plus the
selection metadata (``chosen_cli`` / ``method`` / ``scores`` / ...). When
``None`` the ``CLI_SELECT`` handler returns ``skipped``.
"""


@dataclass(frozen=True, slots=True)
class BodyDriverOutcome:
    """Pillar-internal shape a Body driver returns to the executor.

    ADR-010 §4 S-Vision — kept deliberately small + defined here so
    :mod:`heartbeat` never imports the Body package; the dashboard adapts
    a real Body driver to this protocol. ``succeeded=False`` lands the
    action as ``ActionResult(outcome="failed")``; ``True`` lands
    ``"executed"``.
    """

    succeeded: bool
    summary: str
    metadata: dict[str, object] = field(default_factory=dict)


BodyUseDriver = Callable[["WorldState", ActionDecision], Awaitable[BodyDriverOutcome]]
"""``async (world_state, decision) → BodyDriverOutcome`` — write/click/screenshot.

ADR-010 §4 S-Vision wires the pillar seam. The fat per-platform tool
surface (browser-use / mobile-use / VR-AR — ~250-380 tools) is
S-ToolFleet's scope; the driver receives the model's intent text via
``decision.reasoning`` and the world snapshot, then performs the side
effect through whichever Body subsystem the dashboard wired (``None`` ⇒
``skipped``).
"""


BodyReviewDriver = Callable[["WorldState", ActionDecision], Awaitable[BodyDriverOutcome]]
"""``async (world_state, decision) → BodyDriverOutcome`` — read-only vision parse.

The non-mutating sibling of :data:`BodyUseDriver`. Same signature so the
executor handlers are symmetric; the semantic difference (no write) is
the contract the wired driver must honor.
"""


@dataclass(frozen=True, slots=True)
class ActionResult:
    """The outcome of one :class:`ActionExecutor.execute` call.

    Attributes:
        action: The :class:`LegalAction` that was processed.
        outcome: ``executed`` (side effect committed), ``deferred``
            (intent recorded; later sprint will wire), ``skipped``
            (callable not configured), ``failed`` (callable raised /
            returned an explicit failure signal).
        summary: One-line human-readable status.
        metadata: Action-specific payload (e.g. ``pid``, ``card_id``).
        executed_at: UTC timestamp the result was constructed.
    """

    action: LegalAction
    outcome: ActionOutcome
    summary: str
    metadata: dict[str, object] = field(default_factory=dict)
    executed_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


class ActionExecutor:
    """Dispatch table for the 10 closed ADR-008 §4.4 + ADR-010 §4 action labels.

    Construct once with whichever side-effect callables the host
    process has wired. ``None`` for any callable means "not wired" —
    the corresponding action returns ``ActionResult(outcome="skipped")``
    rather than failing or fabricating a result. This keeps the
    Heartbeat daemon useful + observable even before the dashboard
    completes the Faz H wire.
    """

    def __init__(
        self,
        *,
        telegram_bridge: TelegramBridge | None = None,
        task_starter: TaskStarter | None = None,
        kanban_card_creator: KanbanCardCreator | None = None,
        ideation_manager: IdeationManager | None = None,
        cli_selector: CliSelector | None = None,
        body_use_driver: BodyUseDriver | None = None,
        body_review_driver: BodyReviewDriver | None = None,
    ) -> None:
        self._telegram = telegram_bridge
        self._task_starter = task_starter
        self._kanban_creator = kanban_card_creator
        self._ideation = ideation_manager
        self._cli_selector = cli_selector
        self._body_use = body_use_driver
        self._body_review = body_review_driver

    async def execute(self, decision: ActionDecision, world_state: WorldState) -> ActionResult:
        """Dispatch ``decision`` to its matching handler.

        The deliberation layer is the only authority on which action
        to take; the executor does not second-guess (defensive enum
        coverage notwithstanding).
        """
        action = decision.action
        if action is LegalAction.WAIT:
            return _wait_result(decision)
        if action is LegalAction.SELF_STOP:
            return _self_stop_result(decision)
        if action is LegalAction.OPERATOR_ASK:
            return await self._operator_ask(decision, world_state)
        if action is LegalAction.TASK_START:
            return await self._task_start(decision, world_state)
        if action is LegalAction.KANBAN_SUGGEST:
            return await self._kanban_suggest(decision, world_state)
        if action is LegalAction.SESSION_RESUME:
            return _session_resume_result(decision)
        if action is LegalAction.CLI_SELECT:
            return await self._cli_select(world_state)
        if action is LegalAction.IDEATE:
            return self._ideate(decision, world_state)
        if action is LegalAction.BODY_USE:
            return await self._body_use_action(decision, world_state)
        if action is LegalAction.BODY_REVIEW:
            return await self._body_review_action(decision, world_state)
        # Exhaustive — :func:`assert_never` ensures the enum stays in
        # lockstep with the dispatch table at type-check time and
        # raises at runtime if a new label sneaks in unhandled.
        assert_never(action)

    # ── handlers with side effects ────────────────────────────────

    async def _operator_ask(self, decision: ActionDecision, state: WorldState) -> ActionResult:
        if self._telegram is None:
            return ActionResult(
                action=LegalAction.OPERATOR_ASK,
                outcome="skipped",
                summary="telegram bridge not wired",
            )
        text = decision.reasoning.strip() or "(no reasoning provided)"
        message = TelegramMessage(
            level="info",
            text=f"🤖 Self Jr: {text}",
            session_id=_HEARTBEAT_TELEGRAM_SESSION_ID,
            project_slug=state.last_active_workspace,
        )
        try:
            attempt = await self._telegram.notify(message)
        except Exception as exc:
            _log.warning(
                "heartbeat_operator_ask_raised",
                extra={"error": str(exc)},
            )
            return ActionResult(
                action=LegalAction.OPERATOR_ASK,
                outcome="failed",
                summary=f"telegram bridge raised: {exc}",
            )
        if not attempt.delivered:
            return ActionResult(
                action=LegalAction.OPERATOR_ASK,
                outcome="failed",
                summary=f"delivery failed: {attempt.reason}",
                metadata={"delivered": False},
            )
        return ActionResult(
            action=LegalAction.OPERATOR_ASK,
            outcome="executed",
            summary="operator notified via telegram",
            metadata={
                "delivered": True,
                "chat_id": attempt.chat_id,
            },
        )

    async def _task_start(self, decision: ActionDecision, state: WorldState) -> ActionResult:
        if self._task_starter is None:
            return ActionResult(
                action=LegalAction.TASK_START,
                outcome="skipped",
                summary="task starter not wired",
            )
        project = state.last_active_workspace
        if project is None:
            return ActionResult(
                action=LegalAction.TASK_START,
                outcome="skipped",
                summary="no active workspace to start a task on",
            )
        prd_text = decision.reasoning.strip() or "(heartbeat-initiated task)"
        try:
            pid = await self._task_starter(project, prd_text)
        except Exception as exc:
            _log.warning(
                "heartbeat_task_start_raised",
                extra={"project": project, "error": str(exc)},
            )
            return ActionResult(
                action=LegalAction.TASK_START,
                outcome="failed",
                summary=f"task starter raised: {exc}",
            )
        if pid is None:
            return ActionResult(
                action=LegalAction.TASK_START,
                outcome="failed",
                summary="task starter returned None pid",
            )
        return ActionResult(
            action=LegalAction.TASK_START,
            outcome="executed",
            summary=f"spawned subprocess pid={pid} for project={project}",
            metadata={"pid": pid, "project_slug": project},
        )

    def _ideate(self, decision: ActionDecision, state: WorldState) -> ActionResult:
        if self._ideation is None:
            return _ideate_result(decision)
        text = decision.reasoning.strip()
        if not text:
            return ActionResult(
                action=LegalAction.IDEATE,
                outcome="skipped",
                summary="ideate skipped — empty reasoning",
            )
        try:
            record = self._ideation.record_idea(
                text=text,
                project_slug=state.last_active_workspace,
            )
        except OSError as exc:
            _log.warning(
                "heartbeat_ideate_write_failed",
                extra={"error": str(exc)},
            )
            return ActionResult(
                action=LegalAction.IDEATE,
                outcome="failed",
                summary=f"ideation manager raised: {exc}",
            )
        return ActionResult(
            action=LegalAction.IDEATE,
            outcome="executed",
            summary=(f"recorded {record.size.value} idea {record.idea_id} at {record.path.name}"),
            metadata={
                "idea_id": record.idea_id,
                "title": record.title,
                "size": record.size.value,
                "path": str(record.path),
                "project_slug": record.project_slug,
            },
        )

    async def _kanban_suggest(self, decision: ActionDecision, state: WorldState) -> ActionResult:
        if self._kanban_creator is None:
            return ActionResult(
                action=LegalAction.KANBAN_SUGGEST,
                outcome="skipped",
                summary="kanban card creator not wired",
            )
        project = state.last_active_workspace
        if project is None:
            return ActionResult(
                action=LegalAction.KANBAN_SUGGEST,
                outcome="skipped",
                summary="no active workspace to add a card to",
            )
        reasoning = decision.reasoning.strip()
        title = reasoning.split("\n", 1)[0].split(".", 1)[0][:80].strip()
        if not title:
            title = "Self Jr suggestion"
        body = reasoning or ""
        try:
            card_id = await self._kanban_creator(project, title, body)
        except Exception as exc:
            _log.warning(
                "heartbeat_kanban_suggest_raised",
                extra={"project": project, "error": str(exc)},
            )
            return ActionResult(
                action=LegalAction.KANBAN_SUGGEST,
                outcome="failed",
                summary=f"kanban creator raised: {exc}",
            )
        return ActionResult(
            action=LegalAction.KANBAN_SUGGEST,
            outcome="executed",
            summary=f"suggested kanban card {card_id} on {project}",
            metadata={
                "card_id": card_id,
                "project_slug": project,
                "title": title,
            },
        )

    async def _cli_select(self, state: WorldState) -> ActionResult:
        if self._cli_selector is None:
            return ActionResult(
                action=LegalAction.CLI_SELECT,
                outcome="skipped",
                summary="cli selector not wired",
            )
        try:
            selection = await self._cli_selector(state)
        except Exception as exc:
            _log.warning(
                "heartbeat_cli_select_raised",
                extra={"error": str(exc)},
            )
            return ActionResult(
                action=LegalAction.CLI_SELECT,
                outcome="failed",
                summary=f"cli selector raised: {exc}",
            )
        if selection.cli is None:
            return ActionResult(
                action=LegalAction.CLI_SELECT,
                outcome="skipped",
                summary=selection.reasoning or "no eligible cli for selection",
                metadata=selection.metadata,
            )
        return ActionResult(
            action=LegalAction.CLI_SELECT,
            outcome="executed",
            summary=selection.reasoning,
            metadata=selection.metadata,
        )

    async def _body_use_action(self, decision: ActionDecision, state: WorldState) -> ActionResult:
        return await self._dispatch_body(
            action=LegalAction.BODY_USE,
            driver=self._body_use,
            decision=decision,
            state=state,
        )

    async def _body_review_action(
        self, decision: ActionDecision, state: WorldState
    ) -> ActionResult:
        return await self._dispatch_body(
            action=LegalAction.BODY_REVIEW,
            driver=self._body_review,
            decision=decision,
            state=state,
        )

    async def _dispatch_body(
        self,
        *,
        action: LegalAction,
        driver: BodyUseDriver | BodyReviewDriver | None,
        decision: ActionDecision,
        state: WorldState,
    ) -> ActionResult:
        """Shared wrap for BODY_USE / BODY_REVIEW (ADR-010 §4 S-Vision).

        Both handlers have the same shape — None ⇒ ``skipped``; raise ⇒
        ``failed``; ``BodyDriverOutcome.succeeded=False`` ⇒ ``failed``;
        otherwise ``executed`` — so the wrap is shared instead of
        duplicated across two handlers.
        """
        if driver is None:
            label = "use" if action is LegalAction.BODY_USE else "review"
            return ActionResult(
                action=action,
                outcome="skipped",
                summary=f"body {label} driver not wired",
            )
        try:
            outcome = await driver(state, decision)
        except Exception as exc:
            _log.warning(
                "heartbeat_body_driver_raised",
                extra={"action": action.value, "error": str(exc)},
            )
            return ActionResult(
                action=action,
                outcome="failed",
                summary=f"body driver raised: {exc}",
            )
        if not outcome.succeeded:
            return ActionResult(
                action=action,
                outcome="failed",
                summary=outcome.summary or "body driver reported failure",
                metadata=outcome.metadata,
            )
        return ActionResult(
            action=action,
            outcome="executed",
            summary=outcome.summary or "body action executed",
            metadata=outcome.metadata,
        )


# ── pure handlers (no I/O) ────────────────────────────────────────


def _wait_result(decision: ActionDecision) -> ActionResult:
    return ActionResult(
        action=LegalAction.WAIT,
        outcome="executed",
        summary=decision.reasoning.strip() or "quiet tick",
    )


def _self_stop_result(decision: ActionDecision) -> ActionResult:
    return ActionResult(
        action=LegalAction.SELF_STOP,
        outcome="executed",
        summary=decision.reasoning.strip() or "self-stop requested",
    )


def _session_resume_result(decision: ActionDecision) -> ActionResult:
    return ActionResult(
        action=LegalAction.SESSION_RESUME,
        outcome="deferred",
        summary=(
            decision.reasoning.strip() or "session resume — wired by Faz E (resume store dispatch)"
        ),
    )


def _ideate_result(decision: ActionDecision) -> ActionResult:
    return ActionResult(
        action=LegalAction.IDEATE,
        outcome="deferred",
        summary=(decision.reasoning.strip() or "ideate deferred to Faz F (Yaratma mode)"),
    )
