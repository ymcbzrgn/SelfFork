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
    KanbanCardCreator,
    TaskStarter,
)
from selffork_orchestrator.projects.store import ProjectStore

__all__ = [
    "make_kanban_card_creator",
    "make_task_starter",
]

_log = logging.getLogger(__name__)

# Filename-safe slug regex; collapses anything else to ``-``.
_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def make_task_starter(
    *,
    selffork_script: Path,
    projects_root: Path,
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
        cmd: list[str] = [str(selffork_script), "run", str(prd_path)]
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

    async def _kanban_card_creator(
        project: str, title: str, body: str
    ) -> str:
        def _add() -> str:
            store = ProjectStore(root=projects_root)
            card = store.add_card(project, title=title, body=body)
            return card.id

        return await anyio.to_thread.run_sync(_add)

    return _kanban_card_creator
