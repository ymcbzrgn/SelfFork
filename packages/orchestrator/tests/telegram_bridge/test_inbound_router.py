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
