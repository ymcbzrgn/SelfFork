"""Dashboard-side callable factories for the Heartbeat ActionExecutor (F-AG #3).

S-Auto Faz D shipped :class:`selffork_orchestrator.heartbeat.executor.ActionExecutor`
with four optional callable injection points
(``telegram_bridge`` / ``task_starter`` / ``kanban_card_creator`` /
``ideation_manager``). When the dashboard process boots the
Heartbeat daemon, **these are the production wires** — without them
the executor's ``SEND_TELEGRAM`` / ``TASK_START`` / ``KANBAN_SUGGEST``
handlers return ``skipped`` outcomes and Self Jr can record decisions
but can't act on the world.

This module produces the two coroutines the executor needs
(``TaskStarter`` and ``KanbanCardCreator``) given the dashboard
config; the Telegram bridge is already a long-lived instance on
``app.state.telegram_outbound_bridge``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

import anyio

from selffork_orchestrator.heartbeat.executor import (
    CliSelectionOutcome,
    CliSelector,
    KanbanCardCreator,
    TaskStarter,
)
from selffork_orchestrator.heartbeat.filter import WorldState
from selffork_orchestrator.projects.store import ProjectStore
from selffork_orchestrator.router import (
    CLIRouter,
    CliSelection,
    QuotaExhaustedAcrossFleetError,
    write_affinity_snapshot,
)

__all__ = [
    "make_cli_selector",
    "make_kanban_card_creator",
    "make_task_starter",
]

_log = logging.getLogger(__name__)

# Filename-safe slug regex; collapses anything else to ``-``.
_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _persist_affinity_snapshot(
    workspace: str | None,
    selection: CliSelection,
) -> None:
    """Persist the affinity landscape so Self Jr's ``cli_affinity`` tool can
    read it cross-process (the round-loop subprocess can't open the affinity
    DuckDB; the dashboard is the sole writer). Best-effort — a snapshot
    failure never breaks routing. Skips override/empty selections (no
    affinity scores to surface).
    """
    if workspace is None or not selection.scores:
        return
    try:
        write_affinity_snapshot(workspace, selection.to_metadata())
    except OSError as exc:
        _log.warning(
            "affinity_snapshot_write_failed",
            extra={"workspace": workspace, "error": str(exc)},
        )


def make_task_starter(
    *,
    selffork_script: Path,
    projects_root: Path,
    cli_router: CLIRouter | None = None,
) -> TaskStarter:
    """Build a coroutine that spawns ``selffork run`` for a Heartbeat task.

    Args:
        selffork_script: Absolute path to the ``selffork`` console
            script (same one used by ``POST /api/sessions/run``).
        projects_root: ``~/.selffork/projects/`` root. The Heartbeat
            PRD is written under
            ``<projects_root>/<project>/heartbeat-prds/<timestamp>.md``
            so it lives alongside the project workspace and survives
            the subprocess's own lifecycle.
    """

    async def _task_starter(project: str, prd_text: str) -> int | None:
        safe_project = _SLUG_RE.sub("-", project).strip("-") or "orphan"
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        prd_dir = projects_root / safe_project / "heartbeat-prds"
        try:
            prd_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log.warning(
                "heartbeat_task_starter_mkdir_failed",
                extra={"path": str(prd_dir), "error": str(exc)},
            )
            return None
        prd_path = prd_dir / f"{timestamp}.md"
        try:
            prd_path.write_text(prd_text, encoding="utf-8")
        except OSError as exc:
            _log.warning(
                "heartbeat_task_starter_write_failed",
                extra={"path": str(prd_path), "error": str(exc)},
            )
            return None
        cmd: list[str] = [
            str(selffork_script),
            "run",
            str(prd_path),
            "--project",
            project,
        ]
        # S6 (ADR-006 §4.6): route the task to a CLI + model + effort so
        # Self Jr's affinity-learned selection is actually applied to the
        # spawned session. No router ⇒ the CLI's own config defaults.
        if cli_router is not None:
            try:
                selection = await cli_router.select_cli(workspace=project, task_type=None)
            except QuotaExhaustedAcrossFleetError as exc:
                _log.warning(
                    "heartbeat_task_start_quota_exhausted",
                    extra={"project": project, "error": str(exc)},
                )
                return None
            _persist_affinity_snapshot(project, selection)
            cmd += ["--cli", selection.cli, "--model", selection.model]
            if selection.effort is not None:
                cmd += ["--effort", selection.effort]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except (OSError, FileNotFoundError) as exc:
            _log.warning(
                "heartbeat_task_starter_spawn_failed",
                extra={"cmd": cmd, "error": str(exc)},
            )
            return None
        return proc.pid

    return _task_starter


def make_kanban_card_creator(
    *,
    projects_root: Path,
) -> KanbanCardCreator:
    """Build a coroutine that appends a card to a project's kanban.

    Mirrors ``POST /api/projects/{slug}/kanban/cards`` semantics:
    the card lands in the default column with no explicit order.
    The card id is returned so the audit + checkpoint layers can
    surface it.

    Note (audit-god MINOR #3): we deliberately do NOT sanitise the
    project slug here (unlike ``make_task_starter`` which writes
    files under ``projects_root``). ``ProjectStore.add_card`` calls
    ``validate_slug`` strictly; an invalid slug raises
    :class:`ConfigError` which the executor catches and translates
    into ``outcome="failed"``. Sanitising silently would risk
    matching a different real project (cross-project write) or
    creating ghost board files — failing loudly is the safer
    asymmetry.
    """

    async def _kanban_card_creator(project: str, title: str, body: str) -> str:
        def _add() -> str:
            store = ProjectStore(root=projects_root)
            card = store.add_card(project, title=title, body=body)
            return card.id

        return await anyio.to_thread.run_sync(_add)

    return _kanban_card_creator


def make_cli_selector(router: CLIRouter) -> CliSelector:
    """Build the ``CLI_SELECT`` callable from the S6 router (ADR-006 §4.6).

    The Heartbeat executor invokes this each ``CLI_SELECT`` tick. It reads
    the last-active workspace from the world state and asks the router to
    pick a CLI (operator override → quota filter → affinity argmax).
    Fleet-wide quota exhaustion is translated into ``cli=None`` so the
    executor surfaces a clean ``skipped`` rather than the daemon raising.

    ``task_type`` is ``None`` for now — the Heartbeat has no task
    classifier, so the router's dual-pool backoff scores at the
    workspace/CLI level (the affinity schema carries the dimension for
    when a producer sets it).
    """

    async def _select(state: WorldState) -> CliSelectionOutcome:
        try:
            selection = await router.select_cli(
                workspace=state.last_active_workspace,
                task_type=None,
            )
        except QuotaExhaustedAcrossFleetError as exc:
            return CliSelectionOutcome(
                cli=None,
                reasoning=str(exc),
                metadata={"quota_exhausted": True},
            )
        _persist_affinity_snapshot(state.last_active_workspace, selection)
        return CliSelectionOutcome(
            cli=selection.cli,
            reasoning=selection.reasoning,
            metadata=selection.to_metadata(),
        )

    return _select
