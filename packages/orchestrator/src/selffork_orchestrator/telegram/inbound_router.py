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

if TYPE_CHECKING:
    from selffork_orchestrator.heartbeat.audit import AuditWriter
    from selffork_orchestrator.tools.structured_question import (
        PendingStructuredQuestionStore,
        SqlitePendingStructuredQuestionStore,
    )
from selffork_orchestrator.talk.models import Conversation
from selffork_orchestrator.talk.store import TalkStore
from selffork_orchestrator.telegram.allowlist import AllowList
from selffork_orchestrator.telegram.destructive_notify import (
    CallbackAction,
    parse_callback_data,
)
from selffork_orchestrator.telegram.drafts import TelegramDraftStore
from selffork_orchestrator.voice import (
    NullVoiceBackend,
    VoiceBackend,
    VoiceTranscriptionError,
    VoiceUnavailableError,
)

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
        voice_backend: VoiceBackend | None = None,
        audit_writer: AuditWriter | None = None,
        structured_question_store: (
            PendingStructuredQuestionStore
            | SqlitePendingStructuredQuestionStore
            | None
        ) = None,
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
        # S-Bridge: voice inbound STT backend. ``None`` ⇒ NullVoiceBackend
        # (Telegram voice messages reply with a friendly "not configured"
        # hint instead of silently dropping). Real STT plugs in here.
        self._voice = (
            voice_backend if voice_backend is not None else NullVoiceBackend()
        )
        # S-Bridge: ``/correct`` Telegram command writes a
        # :class:`Correction` row next to the heartbeat audit log. ``None``
        # disables the command cleanly (test contexts that don't need
        # coaching). Production wires :meth:`AuditWriter.default`.
        self._audit_writer = audit_writer
        # S-Bridge CORE: the pending structured-question store the
        # ``/answer`` and ``/cancel`` commands resolve into. ``None``
        # disables those commands cleanly.
        self._structured_question_store = structured_question_store

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
        if norm == "correct":
            return self._handle_correct(args)
        if norm == "answer":
            return await self._handle_answer(args)
        if norm == "cancelq":
            return await self._handle_cancel_question(args)
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

    def _handle_correct(self, args: list[str]) -> CommandOutcome:
        """Append a :class:`Correction` row for a prior audit entry.

        Grammar: ``/correct <audit_idempotency_key> <correction text…>``.
        Operator coaching loop (ADR-010 §coaching) — the Heartbeat
        re-reads corrections next tick and surfaces them as high-weight
        reflex examples; Mind T2 ingest tails the same file. Append-only:
        a correction never rewrites the original entry.
        """
        # Lazy import to avoid the heartbeat.audit → telegram cycle.
        from selffork_orchestrator.heartbeat.audit import Correction

        if self._audit_writer is None:
            return CommandOutcome(
                reply=(
                    "📝 /correct: audit writer not wired — coaching "
                    "trail is disabled on this dashboard boot."
                ),
                command="correct",
                handled=False,
            )
        if len(args) < 2:
            return CommandOutcome(
                reply=(
                    "Usage: /correct <audit_idempotency_key> "
                    "<correction text>"
                ),
                command="correct",
                handled=False,
            )
        key = args[0].strip()
        text = " ".join(args[1:]).strip()
        if not key:
            return CommandOutcome(
                reply="audit_idempotency_key cannot be empty",
                command="correct",
                handled=False,
            )
        if not text:
            return CommandOutcome(
                reply="correction text cannot be empty",
                command="correct",
                handled=False,
            )
        correction = Correction(
            audit_idempotency_key=key,
            correction_text=text,
            source="operator-telegram",
        )
        try:
            self._audit_writer.write_correction(correction)
        except OSError as exc:
            _log.warning(
                "telegram_correct_write_failed",
                extra={"key": key, "reason": str(exc)},
            )
            return CommandOutcome(
                reply=(
                    "📝 /correct: write failed — check disk space "
                    "and audit log permissions."
                ),
                command="correct",
                handled=False,
            )
        return CommandOutcome(
            reply=(
                f"✓ Correction recorded for {key}. "
                "Self Jr will weight this in the next learning pass."
            ),
            command="correct",
            handled=True,
        )

    async def _handle_answer(self, args: list[str]) -> CommandOutcome:
        """Submit an operator answer to a pending structured question.

        Grammar: ``/answer <correlation_id> <option label or text>``.
        S-Bridge CORE — Self Jr emits ``AskUserQuestion`` →
        ``PendingStructuredQuestionStore`` registers + blocks; this
        command resolves it.
        """
        store = self._structured_question_store
        if store is None:
            return CommandOutcome(
                reply=(
                    "📝 /answer: structured-question store not wired — "
                    "Self Jr's AskUserQuestion isn't routed through "
                    "this dashboard."
                ),
                command="answer",
                handled=False,
            )
        if len(args) < 2:
            return CommandOutcome(
                reply="Usage: /answer <correlation_id> <option label or text>",
                command="answer",
                handled=False,
            )
        correlation_id = args[0].strip()
        text = " ".join(args[1:]).strip()
        if not correlation_id:
            return CommandOutcome(
                reply="correlation_id cannot be empty",
                command="answer",
                handled=False,
            )
        if not text:
            return CommandOutcome(
                reply="answer text cannot be empty",
                command="answer",
                handled=False,
            )
        submitted = await store.submit_answer(correlation_id, text)
        if not submitted:
            return CommandOutcome(
                reply=(
                    f"📝 /answer: no pending question {correlation_id!r} "
                    "(already answered, cancelled, or expired)."
                ),
                command="answer",
                handled=False,
            )
        return CommandOutcome(
            reply=(
                f"✓ Answer recorded for {correlation_id}. Self Jr will "
                "resume on its next round."
            ),
            command="answer",
            handled=True,
        )

    async def _handle_cancel_question(
        self, args: list[str],
    ) -> CommandOutcome:
        """Cancel a pending structured question (Self Jr unblocks with no answer).

        Grammar: ``/cancelq <correlation_id>``. Distinct from the
        ``/cancel`` destructive-confirmation command so the two
        cancellation flows don't share a slug (PTB rejects hyphens in
        command names — hence the run-on spelling).
        """
        store = self._structured_question_store
        if store is None:
            return CommandOutcome(
                reply="📝 /cancelq: structured-question store not wired.",
                command="cancelq",
                handled=False,
            )
        if not args:
            return CommandOutcome(
                reply="Usage: /cancelq <correlation_id>",
                command="cancelq",
                handled=False,
            )
        correlation_id = args[0].strip()
        cancelled = await store.cancel(correlation_id)
        if not cancelled:
            return CommandOutcome(
                reply=(
                    f"📝 /cancelq: no pending question {correlation_id!r} "
                    "(already resolved or expired)."
                ),
                command="cancelq",
                handled=False,
            )
        return CommandOutcome(
            reply=(
                f"✓ Cancelled {correlation_id}. Self Jr will proceed "
                "without an operator answer."
            ),
            command="cancelq",
            handled=True,
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

    # ── voice messages (S-Bridge — Telegram-voice-only modality) ──────

    async def handle_voice(
        self,
        *,
        chat_id: int,
        sender: str | None,
        audio: bytes,
        mime: str = "audio/ogg",
    ) -> MessageOutcome:
        """Transcribe Telegram voice and route the text through the chat path.

        Telegram voice attachments arrive as Opus-in-OGG (``audio/ogg``)
        by default; the PTB ``_on_voice`` handler downloads the file
        bytes and forwards them here. We delegate the actual STT to the
        injected :class:`VoiceBackend` so the test seam stays clean.

        Outcomes:

        * Not authorised → ``target="dropped"`` with a refusal reply.
        * Backend unavailable (e.g. whisper not installed,
          ``NullVoiceBackend``) → ``target="dropped"`` with a friendly
          hint; nothing is appended to Talk.
        * Backend ran but failed → ``target="dropped"`` with a generic
          error reply; the underlying exception is logged but not
          surfaced to the operator chat.
        * Successful transcription → forwarded to
          :meth:`handle_message` with the transcript as ``text``; the
          operator sees the same UX as if they had typed it.
        """
        if not self.is_allowed(chat_id):
            return MessageOutcome(
                target="dropped",
                workspace_slug=None,
                reply="⛔ not authorised",
            )
        try:
            transcript = await self._voice.transcribe(audio, mime=mime)
        except VoiceUnavailableError as exc:
            _log.info(
                "telegram_voice_unavailable",
                extra={"chat_id": chat_id, "reason": str(exc)},
            )
            return MessageOutcome(
                target="dropped",
                workspace_slug=None,
                reply=(
                    "🎙️ Voice transcription not configured. Install "
                    "openai-whisper on PATH or wire a VoiceBackend, "
                    "then resend the message."
                ),
            )
        except VoiceTranscriptionError as exc:
            _log.warning(
                "telegram_voice_failed",
                extra={"chat_id": chat_id, "reason": str(exc)},
            )
            return MessageOutcome(
                target="dropped",
                workspace_slug=None,
                reply=(
                    "🎙️ Couldn't transcribe that — try sending the "
                    "voice clip again, or type the message."
                ),
            )
        transcript = transcript.strip()
        if not transcript:
            return MessageOutcome(
                target="dropped",
                workspace_slug=None,
                reply=(
                    "🎙️ Empty transcription — the clip might be "
                    "silent. Try again."
                ),
            )
        # Delegate to the existing text path; same workspace routing +
        # Talk-store ingest + drafts fallback come along for free.
        return await self.handle_message(
            chat_id=chat_id,
            sender=sender,
            text=transcript,
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
    "/correct <audit_idempotency_key> <text> — record an operator "
    "correction for a prior decision\n"
    "/answer <correlation_id> <text> — answer a pending structured "
    "question from Self Jr\n"
    "/cancelq <correlation_id> — cancel a pending structured question "
    "(Self Jr resumes without an answer)\n"
    "/help — this list"
)
