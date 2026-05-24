"""Telegram inbound message router (ADR-006 §4.7.2).

Bridges PTB handlers (callback queries, commands, plain text) to the
SelfFork in-process state — the pending-confirmation store, the Talk
conversation store, and the draft queue. PTB handlers stay thin
(parse + delegate); the actual state machine lives here so it can be
unit-tested without booting a Bot.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

import anyio

from selffork_body.sandbox.pending_confirmations import (
    PendingConfirmation,
    PendingConfirmationStore,
)
from selffork_orchestrator.cli_agent.capabilities import (
    CAPABILITIES,
    capability_for,
)
from selffork_orchestrator.talk.models import Conversation
from selffork_orchestrator.talk.store import TalkStore
from selffork_orchestrator.telegram.allowlist import AllowList
from selffork_orchestrator.telegram.destructive_notify import (
    CallbackAction,
    parse_callback_data,
)
from selffork_orchestrator.telegram.drafts import TelegramDraftStore

if TYPE_CHECKING:
    from selffork_orchestrator.router.override import CliOverrideStore

__all__ = [
    "DEFAULT_EXTEND_HOURS",
    "CallbackOutcome",
    "CommandOutcome",
    "InboundRouter",
    "MessageOutcome",
    "PauseSignal",
]


_log = logging.getLogger(__name__)

DEFAULT_EXTEND_HOURS = 2
"""Hours added by ``Extend 2h`` callback / ``/extend`` command."""


# ── Outcome dataclasses — explicit return types over tuples ──────────────


@dataclasses.dataclass(frozen=True, slots=True)
class CallbackOutcome:
    """Result of handling an inline-keyboard callback."""

    ack: str  # short user-facing answer ("✅ Approved", "❌ Cancelled")
    entry: PendingConfirmation | None
    action: CallbackAction | None
    handled: bool  # False for foreign / unknown callbacks


@dataclasses.dataclass(frozen=True, slots=True)
class CommandOutcome:
    """Result of handling a slash command."""

    reply: str  # human-readable response posted back to the operator chat
    command: str
    handled: bool


@dataclasses.dataclass(frozen=True, slots=True)
class MessageOutcome:
    """Result of routing a plain-text inbound message."""

    target: Literal["talk", "drafts", "dropped"]
    workspace_slug: str | None
    reply: str | None  # operator-facing acknowledgement (None ⇒ no reply)
    conversation_id: UUID | None = None


# ── Pause signal — co-operative round-loop interrupt ─────────────────────


class PauseSignal:
    """Process-local pause flag toggled by ``/pause`` and ``/resume``.

    The round-loop polls this each round; a destructive guard or
    long-running CLI agent reads it between exec calls and stops
    cleanly. Persisted on disk (``~/.selffork/pause.flag``) so a
    restart preserves the request — same fail-safe-NO intent as the
    destructive whitelist.
    """

    def __init__(self, flag_path: object | None = None) -> None:
        from pathlib import Path

        self._path = (
            Path(flag_path)  # type: ignore[arg-type]
            if flag_path is not None
            else Path("~/.selffork/pause.flag").expanduser()
        )

    def request_pause(self, *, reason: str = "operator") -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            f"{datetime.now(tz=UTC).isoformat()} :: {reason}",
            encoding="utf-8",
        )

    def clear(self) -> None:
        import contextlib

        if self._path.is_file():
            with contextlib.suppress(OSError):
                self._path.unlink()

    def is_set(self) -> bool:
        return self._path.is_file()


# ── Router proper ────────────────────────────────────────────────────────


_ConversationFactory = Callable[
    [str | None, str],  # (workspace_slug, title)
    Awaitable[Conversation],
]


class InboundRouter:
    """Holds the dependencies the PTB handlers need.

    Constructed once at dashboard startup and passed into the PTB
    ``Application`` via ``application.bot_data``. Each handler pulls
    the singleton out and forwards work here.
    """

    def __init__(
        self,
        *,
        allowlist: AllowList,
        pending_store: PendingConfirmationStore,
        talk_store: TalkStore | None,
        drafts_store: TelegramDraftStore,
        pause_signal: PauseSignal,
        extend_hours: int = DEFAULT_EXTEND_HOURS,
        conversation_factory: _ConversationFactory | None = None,
        cli_override_store: CliOverrideStore | None = None,
    ) -> None:
        self._allowlist = allowlist
        self._pending = pending_store
        self._talk = talk_store
        self._drafts = drafts_store
        self._pause = pause_signal
        self._extend_hours = extend_hours
        self._conversation_factory = (
            conversation_factory or self._default_conversation_factory
        )
        self._cli_override = cli_override_store

    # ── auth ──────────────────────────────────────────────────────────

    def is_allowed(self, chat_id: int) -> bool:
        """``True`` when ``chat_id`` may issue commands / send messages."""
        return self._allowlist.is_allowed(chat_id)

    # ── callbacks (inline keyboard buttons) ───────────────────────────

    async def handle_callback(
        self,
        *,
        chat_id: int,
        data: str,
    ) -> CallbackOutcome:
        """Route an inline-keyboard callback to the pending store.

        Async so the ``ask`` branch can offload its SQLite write to a
        worker thread (audit fix #4) — running ``TelegramDraftStore.add``
        on the PTB event loop would block the updater under load.

        Returns an outcome rather than raising so the PTB handler can
        always ``answer_callback_query`` (Telegram requires it within
        15 seconds).
        """
        if not self.is_allowed(chat_id):
            return CallbackOutcome(
                ack="⛔ not authorised",
                entry=None,
                action=None,
                handled=False,
            )
        parsed = parse_callback_data(data)
        if parsed is None:
            return CallbackOutcome(
                ack="(ignored)",
                entry=None,
                action=None,
                handled=False,
            )
        action, confirmation_id = parsed
        return await self._apply_callback(action, confirmation_id)

    async def _apply_callback(
        self, action: CallbackAction, cid: str
    ) -> CallbackOutcome:
        if action == "approve":
            entry = self._pending.approve(cid, by="operator-telegram")
            return CallbackOutcome(
                ack="✅ Approved" if entry else "(not found)",
                entry=entry,
                action=action,
                handled=entry is not None,
            )
        if action == "cancel":
            entry = self._pending.cancel(cid, by="operator-telegram")
            return CallbackOutcome(
                ack="❌ Cancelled" if entry else "(not found)",
                entry=entry,
                action=action,
                handled=entry is not None,
            )
        if action == "extend":
            entry = self._pending.extend(
                cid, hours=self._extend_hours, by="operator-telegram"
            )
            return CallbackOutcome(
                ack=(
                    f"⏳ Extended by {self._extend_hours}h"
                    if entry
                    else "(not found)"
                ),
                entry=entry,
                action=action,
                handled=entry is not None,
            )
        # action == "ask"
        entry = self._pending.get(cid)
        if entry is not None:
            summary = entry.command_summary
            # ``TelegramDraftStore.add`` is sync (SQLite write); push it
            # off the PTB updater loop so the bot stays responsive.
            await anyio.to_thread.run_sync(
                lambda: self._drafts.add(
                    chat_id=0,
                    sender="operator",
                    text=f"Asked for context on pending action: {summary}",
                )
            )
        return CallbackOutcome(
            ack="💬 Marked — review in Talk",
            entry=entry,
            action=action,
            handled=entry is not None,
        )

    # ── slash commands ────────────────────────────────────────────────

    async def handle_command(
        self,
        *,
        chat_id: int,
        command: str,
        args: list[str],
    ) -> CommandOutcome:
        """Translate ``/command arg1 arg2`` into a store mutation."""
        if not self.is_allowed(chat_id):
            return CommandOutcome(
                reply="⛔ not authorised", command=command, handled=False
            )
        norm = command.lstrip("/").lower()
        if norm == "pause":
            self._pause.request_pause(reason="telegram")
            return CommandOutcome(
                reply="⏸ Self Jr paused. Active session(s) will stop after the current round.",
                command=norm,
                handled=True,
            )
        if norm == "resume":
            self._pause.clear()
            return CommandOutcome(
                reply="▶️ Pause cleared.", command=norm, handled=True
            )
        if norm == "workspace":
            if not args:
                return CommandOutcome(
                    reply="Usage: /workspace <slug>",
                    command=norm,
                    handled=False,
                )
            slug = args[0]
            reply = await self._set_active_workspace(slug)
            return CommandOutcome(
                reply=reply, command=norm, handled=True
            )
        if norm == "cli":
            return await self._handle_cli_override(args)
        if norm in {"approve", "cancel"}:
            if not args:
                return CommandOutcome(
                    reply=f"Usage: /{norm} <confirmation_id>",
                    command=norm,
                    handled=False,
                )
            cid = args[0]
            cb = await self._apply_callback(norm, cid)  # type: ignore[arg-type]
            return CommandOutcome(
                reply=cb.ack, command=norm, handled=cb.handled
            )
        if norm == "extend":
            if not args:
                return CommandOutcome(
                    reply="Usage: /extend <confirmation_id> [hours]",
                    command=norm,
                    handled=False,
                )
            cid = args[0]
            hours = self._extend_hours
            if len(args) > 1:
                try:
                    hours = int(args[1])
                except ValueError:
                    return CommandOutcome(
                        reply="hours must be an integer",
                        command=norm,
                        handled=False,
                    )
            entry = self._pending.extend(
                cid, hours=hours, by="operator-telegram"
            )
            return CommandOutcome(
                reply=(
                    f"⏳ Extended by {hours}h"
                    if entry
                    else "(not found)"
                ),
                command=norm,
                handled=entry is not None,
            )
        if norm == "help":
            return CommandOutcome(
                reply=_HELP_TEXT,
                command=norm,
                handled=True,
            )
        return CommandOutcome(
            reply=f"unknown command: /{norm} — try /help",
            command=norm,
            handled=False,
        )

    async def _handle_cli_override(self, args: list[str]) -> CommandOutcome:
        """Set a sticky CLI(+model) override for a workspace (ADR-006 §4.6).

        Grammar: ``/cli <cli> [model] [workspace]``. The workspace
        defaults to the last-active Talk workspace; a model is detected
        by membership in the CLI's capability set, so the trailing args
        disambiguate themselves. Sticky, because the dashboard router
        reads it from YAML in a separate process on the next selection.
        """
        store = self._cli_override
        if store is None:
            return CommandOutcome(
                reply="📝 CLI override store offline — can't route right now.",
                command="cli",
                handled=False,
            )
        if not args:
            return CommandOutcome(
                reply="Usage: /cli <cli> [model] [workspace]",
                command="cli",
                handled=False,
            )
        cli = args[0]
        cap = capability_for(cli)
        if cap is None:
            return CommandOutcome(
                reply=f"unknown cli {cli!r}; known: {sorted(CAPABILITIES)}",
                command="cli",
                handled=False,
            )
        rest = args[1:]
        if len(rest) > 2:
            return CommandOutcome(
                reply="Usage: /cli <cli> [model] [workspace]",
                command="cli",
                handled=False,
            )
        model: str | None = None
        explicit_workspace: str | None = None
        if len(rest) == 1:
            # One trailing arg: a known model, else a workspace slug.
            if cap.has_model(rest[0]):
                model = rest[0]
            else:
                explicit_workspace = rest[0]
        elif len(rest) == 2:
            # `<model> <workspace>`: the model must be valid — parity with
            # the set_cli_override tool, which rejects an unknown model
            # instead of silently dropping it.
            if not cap.has_model(rest[0]):
                return CommandOutcome(
                    reply=(
                        f"cli {cli!r} has no model {rest[0]!r}; "
                        f"models: {list(cap.models)}"
                    ),
                    command="cli",
                    handled=False,
                )
            model = rest[0]
            explicit_workspace = rest[1]
        workspace = explicit_workspace
        if workspace is None and self._talk is not None:
            workspace = await self._talk.get_last_active_workspace()
        if workspace is None:
            return CommandOutcome(
                reply=(
                    "No active workspace — say /workspace <slug> first, "
                    "or /cli <cli> [model] <workspace>."
                ),
                command="cli",
                handled=False,
            )
        override = store.set(
            workspace=workspace, cli=cli, model=model, sticky=True
        )
        label = (
            override.cli
            if override.model is None
            else f"{override.cli} ({override.model})"
        )
        return CommandOutcome(
            reply=(
                f"📌 {workspace}: {label} (sticky). "
                "Applies to the next selection."
            ),
            command="cli",
            handled=True,
        )

    async def _set_active_workspace(self, slug: str) -> str:
        """Ensure a Talk conversation pinned to ``slug`` is most-recent.

        Side-effect: appending a no-op marker into a conversation
        bumps ``last_message_at``; that's what
        :meth:`TalkStore.get_last_active_workspace` walks.

        The operator-facing reply just confirms which slug is now active.
        """
        if self._talk is None:
            return f"📝 active workspace noted: {slug} (Talk store offline)"
        # Create a fresh conversation rather than poking an existing one
        # — the marker stays visible in the Talk feed so the operator
        # can see *why* the context switched.
        title = f"Telegram: /workspace {slug}"
        conv = await self._conversation_factory(slug, title)
        await self._talk.append_message(
            conversation_id=conv.id,
            role="operator",
            content=f"/workspace {slug}",
        )
        return f"📌 active workspace: {slug}"

    async def _default_conversation_factory(
        self, workspace_slug: str | None, title: str
    ) -> Conversation:
        if self._talk is None:
            msg = "_default_conversation_factory: TalkStore is not configured"
            raise RuntimeError(msg)
        return await self._talk.create_conversation(
            workspace_slug=workspace_slug, title=title
        )

    # ── plain text messages ───────────────────────────────────────────

    async def handle_message(
        self,
        *,
        chat_id: int,
        sender: str | None,
        text: str,
    ) -> MessageOutcome:
        """Route an unstructured operator message.

        Active workspace exists → append to a Talk conversation pinned
        to that workspace (creating one if needed) and surface to the
        UI via the existing Talk WS event stream.

        No active workspace OR Talk store unavailable → queue as a
        Telegram draft; the Talk page shows a banner on next visit.
        """
        if not self.is_allowed(chat_id):
            return MessageOutcome(
                target="dropped",
                workspace_slug=None,
                reply="⛔ not authorised",
            )
        if self._talk is None:
            self._drafts.add(chat_id=chat_id, sender=sender, text=text)
            return MessageOutcome(
                target="drafts",
                workspace_slug=None,
                reply="📝 Saved (Talk store offline)",
            )
        slug = await self._talk.get_last_active_workspace()
        if slug is None:
            self._drafts.add(chat_id=chat_id, sender=sender, text=text)
            return MessageOutcome(
                target="drafts",
                workspace_slug=None,
                reply=(
                    "📝 No active workspace — saved as draft, "
                    "I'll surface it in Talk."
                ),
            )
        conversations = await self._talk.list_conversations()
        target_conv = next(
            (c for c in conversations if c.workspace_slug == slug),
            None,
        )
        if target_conv is None:
            target_conv = await self._conversation_factory(
                slug, f"Telegram: {slug}"
            )
        await self._talk.append_message(
            conversation_id=target_conv.id,
            role="operator",
            content=text,
        )
        return MessageOutcome(
            target="talk",
            workspace_slug=slug,
            reply=None,
            conversation_id=target_conv.id,
        )


_HELP_TEXT = (
    "SelfFork Telegram commands:\n"
    "/workspace <slug> — set active workspace\n"
    "/cli <cli> [model] [workspace] — route a workspace to a CLI\n"
    "/pause — pause Self Jr after current round\n"
    "/resume — clear pause\n"
    "/approve <id> — approve a pending destructive action\n"
    "/cancel <id> — cancel a pending destructive action\n"
    "/extend <id> [hours] — extend the soft-confirm window\n"
    "/help — this list"
)
