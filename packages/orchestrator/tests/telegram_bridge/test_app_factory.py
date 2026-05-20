"""Tests for the PTB :class:`Application` factory (S3 Phase C).

We don't reach Telegram here — the factory just wires handlers against
a fake bot token. We assert the right handlers got registered and the
router landed in ``bot_data``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
)

from selffork_body.sandbox.pending_confirmations import PendingConfirmationStore
from selffork_orchestrator.telegram.allowlist import AllowList
from selffork_orchestrator.telegram.app import (
    ROUTER_BOT_DATA_KEY,
    TelegramAppConfig,
    build_telegram_application,
    resolve_bot_token,
    resolve_run_mode,
    resolve_webhook_url,
)
from selffork_orchestrator.telegram.drafts import TelegramDraftStore
from selffork_orchestrator.telegram.inbound_router import (
    InboundRouter,
    PauseSignal,
)


def _make_router(tmp_path: Path) -> InboundRouter:
    return InboundRouter(
        allowlist=AllowList(chat_ids=frozenset({1})),
        pending_store=PendingConfirmationStore(audit_path=None),
        talk_store=None,
        drafts_store=TelegramDraftStore(path=tmp_path / "drafts.sqlite"),
        pause_signal=PauseSignal(flag_path=tmp_path / "pause.flag"),
    )


def _handler_kinds(application) -> tuple[set[type], int]:
    """Return (handler classes, total) flattened across PTB groups."""
    handlers: list = []
    for group in application.handlers.values():
        handlers.extend(group)
    return {type(h) for h in handlers}, len(handlers)


def test_factory_registers_all_handler_classes(tmp_path: Path) -> None:
    router = _make_router(tmp_path)
    app = build_telegram_application(
        config=TelegramAppConfig(bot_token="fake-token", mode="polling"),
        router=router,
    )
    kinds, total = _handler_kinds(app)
    assert CallbackQueryHandler in kinds
    assert CommandHandler in kinds
    assert MessageHandler in kinds
    # One callback + 9 commands (workspace/cli/pause/resume/approve/cancel/extend/help/start)
    # + one message handler = 11.
    assert total == 11


def test_factory_stows_router_in_bot_data(tmp_path: Path) -> None:
    router = _make_router(tmp_path)
    app = build_telegram_application(
        config=TelegramAppConfig(bot_token="fake-token", mode="polling"),
        router=router,
    )
    assert app.bot_data[ROUTER_BOT_DATA_KEY] is router


def test_factory_rejects_empty_token(tmp_path: Path) -> None:
    router = _make_router(tmp_path)
    with pytest.raises(ValueError, match="empty bot token"):
        build_telegram_application(
            config=TelegramAppConfig(bot_token="", mode="polling"),
            router=router,
        )


def test_factory_webhook_requires_url(tmp_path: Path) -> None:
    router = _make_router(tmp_path)
    with pytest.raises(ValueError, match="webhook_url"):
        build_telegram_application(
            config=TelegramAppConfig(bot_token="fake", mode="webhook"),
            router=router,
        )


def test_resolve_bot_token_env_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SELFFORK_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert resolve_bot_token() is None
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "legacy")
    assert resolve_bot_token() == "legacy"
    monkeypatch.setenv("SELFFORK_TELEGRAM_BOT_TOKEN", "canonical")
    assert resolve_bot_token() == "canonical"


def test_resolve_run_mode_default_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SELFFORK_TELEGRAM_MODE", raising=False)
    assert resolve_run_mode() == "polling"
    monkeypatch.setenv("SELFFORK_TELEGRAM_MODE", "webhook")
    assert resolve_run_mode() == "webhook"
    monkeypatch.setenv("SELFFORK_TELEGRAM_MODE", "garbage")
    assert resolve_run_mode() == "polling"


def test_resolve_webhook_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELFFORK_TELEGRAM_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_URL", raising=False)
    assert resolve_webhook_url() is None
    monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://legacy.example")
    assert resolve_webhook_url() == "https://legacy.example"
