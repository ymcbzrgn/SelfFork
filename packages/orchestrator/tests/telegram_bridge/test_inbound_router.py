"""Tests for ``InboundRouter`` (S3 Phase C).

The router holds the dependencies the PTB handlers need. We exercise it
without PTB — pure async tests against the public ``handle_callback``,
``handle_command``, and ``handle_message`` API.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from selffork_body.sandbox.destructive_whitelist import (
    CandidateAction,
    DestructiveCategory,
    MatchRule,
)
from selffork_body.sandbox.pending_confirmations import (
    PendingConfirmationStore,
)
from selffork_orchestrator.cli_agent.capabilities import capability_for
from selffork_orchestrator.dashboard.settings.store import YamlSettingsStore
from selffork_orchestrator.router.override import (
    CliOverrideStore,
    StickyOverrides,
)
from selffork_orchestrator.talk.store import TalkStore
from selffork_orchestrator.telegram.allowlist import AllowList
from selffork_orchestrator.telegram.drafts import TelegramDraftStore
from selffork_orchestrator.telegram.inbound_router import (
    InboundRouter,
    PauseSignal,
)

ALLOWED_CHAT = 12345
DENIED_CHAT = 99999


@pytest.fixture
def allowlist() -> AllowList:
    return AllowList(chat_ids=frozenset({ALLOWED_CHAT}))


@pytest.fixture
def pending_store() -> PendingConfirmationStore:
    return PendingConfirmationStore(audit_path=None)


@pytest.fixture
async def talk_store(tmp_path: Path) -> TalkStore:
    store = TalkStore(db_path=tmp_path / "talk.sqlite")
    await store.setup()
    yield store
    await store.teardown()


@pytest.fixture
def drafts_store(tmp_path: Path) -> TelegramDraftStore:
    return TelegramDraftStore(path=tmp_path / "drafts.sqlite")


@pytest.fixture
def pause_signal(tmp_path: Path) -> PauseSignal:
    return PauseSignal(flag_path=tmp_path / "pause.flag")


@pytest.fixture
def category() -> DestructiveCategory:
    return DestructiveCategory(
        id="prod_deploy",
        description="PROD push",
        confirm_window_hours=4,
        match_any=(
            MatchRule(tool="git", args_contains=("push", "origin", "main")),
        ),
    )


@pytest.fixture
def cli_override_store(tmp_path: Path) -> CliOverrideStore:
    return CliOverrideStore(
        sticky_store=YamlSettingsStore(
            path=tmp_path / "cli_override.yaml",
            schema=StickyOverrides,
            default_factory=StickyOverrides,
        )
    )


@pytest.fixture
def router(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> InboundRouter:
    return InboundRouter(
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )


# ── callbacks ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_approve_flips_status(
    router: InboundRouter,
    pending_store: PendingConfirmationStore,
    category: DestructiveCategory,
) -> None:
    entry = pending_store.request(
        category=category,
        action=CandidateAction(tool="git", args=("push", "origin", "main")),
        workspace_slug="demo",
    )
    outcome = await router.handle_callback(
        chat_id=ALLOWED_CHAT,
        data=f"pending:approve:{entry.id}",
    )
    assert outcome.handled
    assert outcome.action == "approve"
    final = pending_store.get(entry.id)
    assert final is not None and final.status == "approved"
    assert "Approved" in outcome.ack


@pytest.mark.asyncio
async def test_callback_cancel_flips_status(
    router: InboundRouter,
    pending_store: PendingConfirmationStore,
    category: DestructiveCategory,
) -> None:
    entry = pending_store.request(
        category=category,
        action=CandidateAction(tool="git", args=("push", "origin", "main")),
        workspace_slug="demo",
    )
    outcome = await router.handle_callback(
        chat_id=ALLOWED_CHAT,
        data=f"pending:cancel:{entry.id}",
    )
    assert outcome.handled
    final = pending_store.get(entry.id)
    assert final is not None and final.status == "cancelled"


@pytest.mark.asyncio
async def test_callback_extend_pushes_window(
    router: InboundRouter,
    pending_store: PendingConfirmationStore,
    category: DestructiveCategory,
) -> None:
    entry = pending_store.request(
        category=category,
        action=CandidateAction(tool="git", args=("push", "origin", "main")),
        workspace_slug=None,
    )
    outcome = await router.handle_callback(
        chat_id=ALLOWED_CHAT,
        data=f"pending:extend:{entry.id}",
    )
    assert outcome.handled
    assert outcome.action == "extend"
    # status stays pending — extend just bumps expires_at
    final = pending_store.get(entry.id)
    assert final is not None and final.status == "pending"


@pytest.mark.asyncio
async def test_callback_ask_queues_draft_off_loop(
    router: InboundRouter,
    pending_store: PendingConfirmationStore,
    drafts_store,
    category: DestructiveCategory,
) -> None:
    """``ask`` branch goes through ``anyio.to_thread`` and lands in drafts."""
    entry = pending_store.request(
        category=category,
        action=CandidateAction(tool="git", args=("push", "origin", "main")),
        workspace_slug="demo",
    )
    outcome = await router.handle_callback(
        chat_id=ALLOWED_CHAT,
        data=f"pending:ask:{entry.id}",
    )
    assert outcome.handled
    drafts = drafts_store.list_unclaimed()
    assert any(
        "Asked for context" in d.text and entry.command_summary in d.text
        for d in drafts
    )


@pytest.mark.asyncio
async def test_callback_unauthorised_rejects(router: InboundRouter) -> None:
    outcome = await router.handle_callback(
        chat_id=DENIED_CHAT,
        data="pending:approve:any",
    )
    assert not outcome.handled
    assert "authorised" in outcome.ack


@pytest.mark.asyncio
async def test_callback_foreign_namespace_ignored(router: InboundRouter) -> None:
    outcome = await router.handle_callback(
        chat_id=ALLOWED_CHAT,
        data="other:approve:abc",
    )
    assert not outcome.handled


# ── commands ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_command_pause_writes_flag(
    router: InboundRouter, pause_signal: PauseSignal
) -> None:
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="pause", args=[]
    )
    assert outcome.handled
    assert pause_signal.is_set()


@pytest.mark.asyncio
async def test_command_resume_clears_flag(
    router: InboundRouter, pause_signal: PauseSignal
) -> None:
    pause_signal.request_pause(reason="test")
    assert pause_signal.is_set()
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="resume", args=[]
    )
    assert outcome.handled
    assert not pause_signal.is_set()


@pytest.mark.asyncio
async def test_command_workspace_sets_active(
    router: InboundRouter, talk_store: TalkStore
) -> None:
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="workspace", args=["alpha"]
    )
    assert outcome.handled
    slug = await talk_store.get_last_active_workspace()
    assert slug == "alpha"


@pytest.mark.asyncio
async def test_command_cli_sets_sticky_override(
    router: InboundRouter, cli_override_store: CliOverrideStore
) -> None:
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="cli", args=["codex", "projectx"]
    )
    assert outcome.handled
    override = cli_override_store.peek("projectx")
    assert override is not None
    assert override.cli == "codex"
    assert override.model is None
    assert override.sticky is True


@pytest.mark.asyncio
async def test_command_cli_with_model(
    router: InboundRouter, cli_override_store: CliOverrideStore
) -> None:
    cap = capability_for("codex")
    assert cap is not None
    model = cap.models[0]
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="cli", args=["codex", model, "projectx"]
    )
    assert outcome.handled
    override = cli_override_store.peek("projectx")
    assert override is not None
    assert override.cli == "codex"
    assert override.model == model


@pytest.mark.asyncio
async def test_command_cli_uses_last_active_workspace(
    router: InboundRouter,
    talk_store: TalkStore,
    cli_override_store: CliOverrideStore,
) -> None:
    await router.handle_command(
        chat_id=ALLOWED_CHAT, command="workspace", args=["alpha"]
    )
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="cli", args=["codex"]
    )
    assert outcome.handled
    override = cli_override_store.peek("alpha")
    assert override is not None
    assert override.cli == "codex"
    assert override.model is None


@pytest.mark.asyncio
async def test_command_cli_unknown_cli_rejected(
    router: InboundRouter, cli_override_store: CliOverrideStore
) -> None:
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="cli", args=["bogus", "projectx"]
    )
    assert not outcome.handled
    assert "unknown cli" in outcome.reply
    assert "known" in outcome.reply
    assert cli_override_store.peek("projectx") is None


@pytest.mark.asyncio
async def test_command_cli_without_workspace_rejected(
    router: InboundRouter,
) -> None:
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="cli", args=["codex"]
    )
    assert not outcome.handled
    assert "workspace" in outcome.reply.lower()


@pytest.mark.asyncio
async def test_command_cli_override_persists_across_store_instances(
    router: InboundRouter, tmp_path: Path
) -> None:
    # The dashboard router reads overrides from YAML in a SEPARATE process;
    # a sticky write must be visible to a fresh store over the same file
    # (a single-turn, in-memory override would not survive this boundary).
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="cli", args=["codex", "projectx"]
    )
    assert outcome.handled
    reread = CliOverrideStore(
        sticky_store=YamlSettingsStore(
            path=tmp_path / "cli_override.yaml",
            schema=StickyOverrides,
            default_factory=StickyOverrides,
        )
    )
    override = reread.get_active("projectx")
    assert override is not None
    assert override.cli == "codex"
    assert override.sticky is True


@pytest.mark.asyncio
async def test_command_cli_two_arg_rejects_unknown_model(
    router: InboundRouter, cli_override_store: CliOverrideStore
) -> None:
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT,
        command="cli",
        args=["codex", "not-a-real-model", "projectx"],
    )
    assert not outcome.handled
    assert "has no model" in outcome.reply
    assert cli_override_store.peek("projectx") is None


@pytest.mark.asyncio
async def test_command_help_returns_usage(router: InboundRouter) -> None:
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="help", args=[]
    )
    assert outcome.handled
    assert "/workspace" in outcome.reply
    assert "/approve" in outcome.reply


@pytest.mark.asyncio
async def test_command_unknown_rejected(router: InboundRouter) -> None:
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="nonexistent", args=[]
    )
    assert not outcome.handled
    assert "unknown" in outcome.reply.lower()


@pytest.mark.asyncio
async def test_command_unauthorised_rejects(router: InboundRouter) -> None:
    outcome = await router.handle_command(
        chat_id=DENIED_CHAT, command="pause", args=[]
    )
    assert not outcome.handled


# ── plain text messages ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_message_with_no_active_workspace_goes_to_drafts(
    router: InboundRouter, drafts_store: TelegramDraftStore
) -> None:
    outcome = await router.handle_message(
        chat_id=ALLOWED_CHAT, sender="yamac", text="hi jr"
    )
    assert outcome.target == "drafts"
    assert drafts_store.count_unclaimed() == 1


@pytest.mark.asyncio
async def test_message_with_active_workspace_injects_into_talk(
    router: InboundRouter, talk_store: TalkStore
) -> None:
    # Establish an active workspace first via /workspace.
    await router.handle_command(
        chat_id=ALLOWED_CHAT, command="workspace", args=["beta"]
    )
    outcome = await router.handle_message(
        chat_id=ALLOWED_CHAT, sender="yamac", text="continue the build"
    )
    assert outcome.target == "talk"
    assert outcome.workspace_slug == "beta"
    # Confirm a message landed in the conversation.
    assert outcome.conversation_id is not None
    messages = await talk_store.list_messages(
        conversation_id=outcome.conversation_id
    )
    assert any(m.content == "continue the build" for m in messages)


@pytest.mark.asyncio
async def test_message_unauthorised_dropped(
    router: InboundRouter, drafts_store: TelegramDraftStore
) -> None:
    outcome = await router.handle_message(
        chat_id=DENIED_CHAT, sender="ghost", text="hi"
    )
    assert outcome.target == "dropped"
    assert drafts_store.count_unclaimed() == 0


# ── voice (S-Bridge) ─────────────────────────────────────────────────────


from selffork_orchestrator.voice import (  # noqa: E402
    NullVoiceBackend,
    VoiceBackend,
    VoiceTranscriptionError,
    VoiceUnavailableError,
)


class _FakeVoiceBackend:
    """STT test double — returns a canned transcript or raises."""

    def __init__(
        self,
        *,
        transcript: str | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._transcript = transcript
        self._exc = exc

    async def transcribe(
        self, audio: bytes, *, mime: str = "audio/ogg"
    ) -> str:
        del audio, mime
        if self._exc is not None:
            raise self._exc
        assert self._transcript is not None
        return self._transcript


def _voice_router(
    voice_backend: VoiceBackend,
    *,
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> InboundRouter:
    return InboundRouter(
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
        voice_backend=voice_backend,
    )


@pytest.mark.asyncio
async def test_voice_unauthorised_dropped(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> None:
    router = _voice_router(
        _FakeVoiceBackend(transcript="should not be reached"),
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_voice(
        chat_id=DENIED_CHAT,
        sender="ghost",
        audio=b"<ogg-bytes>",
        mime="audio/ogg",
    )
    assert outcome.target == "dropped"
    assert "not authorised" in (outcome.reply or "")


@pytest.mark.asyncio
async def test_voice_null_backend_replies_with_hint(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> None:
    router = _voice_router(
        _FakeVoiceBackend(exc=VoiceUnavailableError("no backend")),
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_voice(
        chat_id=ALLOWED_CHAT,
        sender="yamac",
        audio=b"<ogg-bytes>",
        mime="audio/ogg",
    )
    assert outcome.target == "dropped"
    assert "not configured" in (outcome.reply or "")


@pytest.mark.asyncio
async def test_voice_transcription_error_replies_with_retry_hint(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> None:
    router = _voice_router(
        _FakeVoiceBackend(
            exc=VoiceTranscriptionError("whisper exited 1"),
        ),
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_voice(
        chat_id=ALLOWED_CHAT,
        sender="yamac",
        audio=b"<ogg-bytes>",
        mime="audio/ogg",
    )
    assert outcome.target == "dropped"
    assert "Couldn't transcribe" in (outcome.reply or "")


@pytest.mark.asyncio
async def test_voice_empty_transcript_dropped(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> None:
    router = _voice_router(
        _FakeVoiceBackend(transcript="   "),
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_voice(
        chat_id=ALLOWED_CHAT,
        sender="yamac",
        audio=b"<ogg-bytes>",
        mime="audio/ogg",
    )
    assert outcome.target == "dropped"
    assert "Empty" in (outcome.reply or "")


@pytest.mark.asyncio
async def test_voice_success_routes_through_handle_message(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> None:
    router = _voice_router(
        _FakeVoiceBackend(transcript="continue the build"),
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    await router.handle_command(
        chat_id=ALLOWED_CHAT, command="workspace", args=["gamma"],
    )
    outcome = await router.handle_voice(
        chat_id=ALLOWED_CHAT,
        sender="yamac",
        audio=b"<ogg-bytes>",
        mime="audio/ogg",
    )
    assert outcome.target == "talk"
    assert outcome.workspace_slug == "gamma"
    assert outcome.conversation_id is not None
    messages = await talk_store.list_messages(
        conversation_id=outcome.conversation_id,
    )
    assert any(m.content == "continue the build" for m in messages)


def test_inbound_router_voice_backend_defaults_to_null(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> None:
    """Constructing without ``voice_backend`` MUST install NullVoiceBackend."""
    router = InboundRouter(
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    assert isinstance(router._voice, NullVoiceBackend)


# ── /correct (S-Bridge coaching loop) ────────────────────────────────────


import json as _json  # noqa: E402

from selffork_orchestrator.heartbeat.audit import (  # noqa: E402
    AuditWriter,
)


@pytest.fixture
def audit_writer(tmp_path: Path) -> AuditWriter:
    return AuditWriter(path=tmp_path / "audit" / "heartbeat.jsonl")


def _coaching_router(
    audit_writer: AuditWriter | None,
    *,
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> InboundRouter:
    return InboundRouter(
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
        audit_writer=audit_writer,
    )


@pytest.mark.asyncio
async def test_correct_unauthorised(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
    audit_writer: AuditWriter,
) -> None:
    router = _coaching_router(
        audit_writer,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_command(
        chat_id=DENIED_CHAT,
        command="correct",
        args=["KEY123", "wrong call"],
    )
    assert "not authorised" in outcome.reply
    assert outcome.handled is False
    assert not audit_writer.corrections_path.exists()


@pytest.mark.asyncio
async def test_correct_without_audit_writer_replies_clean(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> None:
    router = _coaching_router(
        None,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT,
        command="correct",
        args=["KEY123", "should not write"],
    )
    assert outcome.handled is False
    assert "audit writer not wired" in outcome.reply


@pytest.mark.asyncio
async def test_correct_missing_args(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
    audit_writer: AuditWriter,
) -> None:
    router = _coaching_router(
        audit_writer,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="correct", args=[],
    )
    assert outcome.handled is False
    assert "Usage" in outcome.reply

    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="correct", args=["KEY-only"],
    )
    assert outcome.handled is False
    assert "Usage" in outcome.reply


@pytest.mark.asyncio
async def test_correct_appends_jsonl_row(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
    audit_writer: AuditWriter,
) -> None:
    router = _coaching_router(
        audit_writer,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT,
        command="correct",
        args=[
            "AUDIT-KEY-001",
            "should",
            "have",
            "rolled",
            "back",
            "instead",
        ],
    )
    assert outcome.handled is True
    assert "Correction recorded for AUDIT-KEY-001" in outcome.reply
    # Read the JSONL row back.
    raw = audit_writer.corrections_path.read_text(encoding="utf-8").strip()
    rows = [_json.loads(line) for line in raw.splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["audit_idempotency_key"] == "AUDIT-KEY-001"
    assert rows[0]["correction_text"] == "should have rolled back instead"
    assert rows[0]["source"] == "operator-telegram"


@pytest.mark.asyncio
async def test_correct_appends_multiple_rows(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
    audit_writer: AuditWriter,
) -> None:
    router = _coaching_router(
        audit_writer,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    for idx in range(3):
        await router.handle_command(
            chat_id=ALLOWED_CHAT,
            command="correct",
            args=[f"KEY-{idx}", f"correction-{idx}"],
        )
    rows = audit_writer.corrections_path.read_text(encoding="utf-8")
    lines = [line for line in rows.splitlines() if line.strip()]
    assert len(lines) == 3


@pytest.mark.asyncio
async def test_correct_listed_in_help(
    audit_writer: AuditWriter,
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> None:
    router = _coaching_router(
        audit_writer,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="help", args=[],
    )
    assert outcome.handled is True
    assert "/correct" in outcome.reply


# ── /answer + /cancelq (S-Bridge CORE) ───────────────────────────────────


from selffork_orchestrator.tools.structured_question import (  # noqa: E402
    PendingStructuredQuestionStore,
)


@pytest.fixture
def structured_question_store() -> PendingStructuredQuestionStore:
    return PendingStructuredQuestionStore()


def _question_router(
    store: PendingStructuredQuestionStore | None,
    *,
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> InboundRouter:
    return InboundRouter(
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
        structured_question_store=store,
    )


@pytest.mark.asyncio
async def test_answer_unauthorised(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
    structured_question_store: PendingStructuredQuestionStore,
) -> None:
    router = _question_router(
        structured_question_store,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_command(
        chat_id=DENIED_CHAT, command="answer", args=["abc", "yes"],
    )
    assert outcome.handled is False
    assert "not authorised" in outcome.reply


@pytest.mark.asyncio
async def test_answer_without_store_replies_clean(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> None:
    router = _question_router(
        None,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="answer", args=["abc", "yes"],
    )
    assert outcome.handled is False
    assert "not wired" in outcome.reply


@pytest.mark.asyncio
async def test_answer_missing_args(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
    structured_question_store: PendingStructuredQuestionStore,
) -> None:
    router = _question_router(
        structured_question_store,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="answer", args=[],
    )
    assert outcome.handled is False
    assert "Usage" in outcome.reply
    outcome2 = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="answer", args=["onlykey"],
    )
    assert outcome2.handled is False
    assert "Usage" in outcome2.reply


@pytest.mark.asyncio
async def test_answer_unknown_correlation(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
    structured_question_store: PendingStructuredQuestionStore,
) -> None:
    router = _question_router(
        structured_question_store,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT,
        command="answer",
        args=["nosuch", "Yes"],
    )
    assert outcome.handled is False
    assert "no pending question" in outcome.reply


@pytest.mark.asyncio
async def test_answer_resolves_pending_question(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
    structured_question_store: PendingStructuredQuestionStore,
) -> None:
    router = _question_router(
        structured_question_store,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    entry = await structured_question_store.register(
        payload={"questions": [{"q": "Q"}]},
    )
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT,
        command="answer",
        args=[entry.correlation_id, "ship", "it"],
    )
    assert outcome.handled is True
    assert entry.correlation_id in outcome.reply
    stored = await structured_question_store.get(entry.correlation_id)
    assert stored is not None
    assert stored.answer == "ship it"


@pytest.mark.asyncio
async def test_cancelq_resolves_pending_question(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
    structured_question_store: PendingStructuredQuestionStore,
) -> None:
    router = _question_router(
        structured_question_store,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    entry = await structured_question_store.register(payload={"q": "x"})
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT,
        command="cancelq",
        args=[entry.correlation_id],
    )
    assert outcome.handled is True
    assert entry.correlation_id in outcome.reply
    stored = await structured_question_store.get(entry.correlation_id)
    assert stored is not None and stored.cancelled is True


@pytest.mark.asyncio
async def test_cancelq_without_store_replies_clean(
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> None:
    router = _question_router(
        None,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="cancelq", args=["abc"],
    )
    assert outcome.handled is False
    assert "not wired" in outcome.reply


@pytest.mark.asyncio
async def test_answer_listed_in_help(
    structured_question_store: PendingStructuredQuestionStore,
    allowlist: AllowList,
    pending_store: PendingConfirmationStore,
    talk_store: TalkStore,
    drafts_store: TelegramDraftStore,
    pause_signal: PauseSignal,
    cli_override_store: CliOverrideStore,
) -> None:
    router = _question_router(
        structured_question_store,
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
    )
    outcome = await router.handle_command(
        chat_id=ALLOWED_CHAT, command="help", args=[],
    )
    assert outcome.handled is True
    assert "/answer" in outcome.reply
    assert "/cancelq" in outcome.reply
