"""Theater event producer — the round-loop's bridge to the theater store.

``StoreTheaterProducer`` is the object the round-loop (:class:`Session`)
calls to surface its activity in the Workspace "Live Run" theater: CLI
output line-by-line, Self Jr's compacted thought each round, and the
loop's lifecycle (register on start, clear on end). It writes to a
:class:`~selffork_orchestrator.theater.store.TheaterStore`; the dashboard
process tails that store independently.

``NullTheaterProducer`` is the no-op default — used for orphan runs (no
``--project``, so no workspace to attach a theater to) and any caller
that has not wired a theater. The round-loop always holds a
``TheaterProducer`` and never branches on ``None``, mirroring the
``NullTelegramBridge`` default in :mod:`selffork_orchestrator.cli`.

The theater is best-effort observability: ``StoreTheaterProducer``
swallows and logs every store error so a theater glitch can never crash
a real session.
"""

from __future__ import annotations

from typing import Protocol

from selffork_orchestrator.theater.models import (
    CliOutputKind,
    CliOutputPayload,
)
from selffork_orchestrator.theater.store import TheaterStore
from selffork_orchestrator.theater.thought import parse_thought
from selffork_shared.logging import get_logger

__all__ = [
    "NullTheaterProducer",
    "StoreTheaterProducer",
    "TheaterProducer",
]

_log = get_logger(__name__)


class TheaterProducer(Protocol):
    """What the round-loop calls to surface itself in the theater."""

    async def loop_started(self) -> None:
        """Register the loop as active (theater header + Live Loop hero)."""
        ...

    async def cli_output(self, text: str, *, kind: CliOutputKind = "stdout") -> None:
        """Append one CLI output / jr-prompt chunk to the theater stream."""
        ...

    async def thought(self, reply: str, *, turn: int) -> None:
        """Surface round-``turn``'s Jr reply as a thought; advance the turn."""
        ...

    async def loop_ended(self) -> None:
        """Clear the loop from the active set — called when it ends."""
        ...


class NullTheaterProducer:
    """No-op producer — the safe default when no theater is wired."""

    async def loop_started(self) -> None:
        return None

    async def cli_output(self, text: str, *, kind: CliOutputKind = "stdout") -> None:
        return None

    async def thought(self, reply: str, *, turn: int) -> None:
        return None

    async def loop_ended(self) -> None:
        return None


class StoreTheaterProducer:
    """Theater producer that writes to a :class:`TheaterStore`.

    One instance per round-loop, constructed with the loop's identity
    (session, workspace, CLI) so the round-loop's call sites pass only
    per-event data. Every method is best-effort — store errors are
    logged and swallowed, never raised into the round-loop.
    """

    def __init__(
        self,
        *,
        store: TheaterStore,
        session_id: str,
        workspace_slug: str,
        workspace_name: str,
        cli: str,
    ) -> None:
        self._store = store
        self._session_id = session_id
        self._workspace_slug = workspace_slug
        self._workspace_name = workspace_name
        self._cli = cli

    async def loop_started(self) -> None:
        try:
            await self._store.register_loop(
                session_id=self._session_id,
                workspace_slug=self._workspace_slug,
                workspace_name=self._workspace_name,
                cli=self._cli,
            )
        except Exception as exc:  # best-effort observability
            _log.warning("theater_loop_started_failed", error=str(exc))

    async def cli_output(self, text: str, *, kind: CliOutputKind = "stdout") -> None:
        try:
            await self._store.append_event(
                workspace_slug=self._workspace_slug,
                session_id=self._session_id,
                kind="cli_output",
                payload=CliOutputPayload(kind=kind, text=text).model_dump(),
            )
        except Exception as exc:  # best-effort observability
            _log.debug("theater_cli_output_failed", error=str(exc))

    async def thought(self, reply: str, *, turn: int) -> None:
        try:
            parsed = parse_thought(reply)
            # Keep the loop's turn current every round, even when the
            # reply carries no narration (parses to None).
            await self._store.touch_loop(
                session_id=self._session_id,
                turn=turn,
                last_thought=(parsed.summary if parsed is not None else None),
            )
            if parsed is not None:
                await self._store.append_event(
                    workspace_slug=self._workspace_slug,
                    session_id=self._session_id,
                    kind="thought",
                    payload=parsed.model_dump(),
                )
        except Exception as exc:  # best-effort observability
            _log.debug("theater_thought_failed", error=str(exc))

    async def loop_ended(self) -> None:
        try:
            await self._store.clear_loop(self._session_id)
        except Exception as exc:  # best-effort observability
            _log.warning("theater_loop_ended_failed", error=str(exc))
