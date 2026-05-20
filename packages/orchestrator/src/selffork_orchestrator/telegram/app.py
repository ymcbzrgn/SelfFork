"""PTB v22.7 :class:`Application` factory + lifecycle (S3 Phase C).

ADR-006 §4.7 establishes Telegram as the operator's mobile surface for
two-way conversation with Self Jr. This module wires PTB to the inbound
:class:`InboundRouter` so plain text, slash commands, and inline
callbacks all reach the SelfFork in-process state.

Two startup modes:

* ``polling`` (dev default) — PTB owns the loop, long-polls Telegram.
  Suitable for laptops, CI smoke tests, and operators without a
  public webhook URL.
* ``webhook`` (prod) — Telegram POSTs updates to the dashboard FastAPI
  server's ``/api/telegram/webhook`` endpoint; Phase E wires the
  reverse path so PTB stays a pure event processor here.

In both modes the same handler set runs — the route just differs.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Final, Literal

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from selffork_orchestrator.telegram.destructive_notify import CALLBACK_PREFIX
from selffork_orchestrator.telegram.inbound_router import InboundRouter

__all__ = [
    "ROUTER_BOT_DATA_KEY",
    "TelegramAppConfig",
    "TelegramRunMode",
    "build_telegram_application",
    "register_inbound_handlers",
]


_log = logging.getLogger(__name__)

TelegramRunMode = Literal["polling", "webhook"]
"""How the PTB application receives updates from Telegram."""

ROUTER_BOT_DATA_KEY: Final[str] = "selffork_inbound_router"
"""Slot in ``Application.bot_data`` where :class:`InboundRouter` lives."""


@dataclass(frozen=True, slots=True)
class TelegramAppConfig:
    """Inputs for :func:`build_telegram_application`."""

    bot_token: str
    mode: TelegramRunMode = "polling"
    webhook_url: str | None = None  # required when mode == "webhook"
    drop_pending_updates: bool = True


def build_telegram_application(
    *,
    config: TelegramAppConfig,
    router: InboundRouter,
) -> Application:  # type: ignore[type-arg]
    """Construct a fully-configured PTB v22.7 :class:`Application`.

    The application is NOT started — callers (the dashboard lifespan)
    own ``initialize / start / updater.start_polling / set_webhook /
    shutdown`` to keep this factory pure.
    """
    if not config.bot_token.strip():
        msg = "build_telegram_application: empty bot token"
        raise ValueError(msg)
    if config.mode == "webhook" and not (config.webhook_url and config.webhook_url.strip()):
        msg = "build_telegram_application: webhook mode requires webhook_url"
        raise ValueError(msg)

    application = (
        Application.builder()
        .token(config.bot_token)
        .build()
    )
    application.bot_data[ROUTER_BOT_DATA_KEY] = router
    register_inbound_handlers(application)
    return application


def register_inbound_handlers(application: Application) -> None:  # type: ignore[type-arg]
    """Attach the three handler classes (callback / command / message).

    Exposed so tests can register the same handlers against a stub
    application without rebuilding the bot.
    """
    application.add_handler(
        CallbackQueryHandler(
            _on_callback_query,
            pattern=rf"^{CALLBACK_PREFIX}:",
        )
    )
    # PTB doesn't expose a one-handler-many-commands helper, so register
    # each slash command explicitly. Keep the list in sync with
    # :class:`InboundRouter.handle_command`.
    for command in (
        "workspace",
        "cli",
        "pause",
        "resume",
        "approve",
        "cancel",
        "extend",
        "help",
        "start",  # Telegram clients send /start on first contact
    ):
        application.add_handler(CommandHandler(command, _on_command))
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            _on_message,
        )
    )


# ── PTB handler implementations ──────────────────────────────────────────


def _resolve_router(context: ContextTypes.DEFAULT_TYPE) -> InboundRouter | None:
    """Look up the router stowed in ``Application.bot_data``."""
    router = context.application.bot_data.get(ROUTER_BOT_DATA_KEY)
    if isinstance(router, InboundRouter):
        return router
    _log.warning(
        "telegram_inbound_router_missing",
        extra={"bot_data_keys": list(context.application.bot_data.keys())},
    )
    return None


async def _on_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Translate inline-keyboard taps into pending-store mutations."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    router = _resolve_router(context)
    if router is None:
        await query.answer("⚠️ bridge unwired", show_alert=False)
        return
    chat = query.message.chat if query.message else None
    chat_id = chat.id if chat is not None else 0
    outcome = await router.handle_callback(chat_id=chat_id, data=query.data)
    # Acknowledge first (Telegram requires a response within 15 seconds)
    await query.answer(outcome.ack, show_alert=False)


async def _on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch ``/command arg…`` to :meth:`InboundRouter.handle_command`."""
    message = update.effective_message
    if message is None or message.text is None:
        return
    router = _resolve_router(context)
    if router is None:
        await message.reply_text("⚠️ bridge unwired")
        return
    raw = message.text.strip()
    if not raw.startswith("/"):
        return
    parts = raw.split()
    # Strip ``@BotUsername`` suffix Telegram appends in groups
    head = parts[0].split("@", 1)[0]
    command = head[1:]  # drop leading slash
    args = parts[1:]
    chat = message.chat
    chat_id = chat.id if chat is not None else 0
    outcome = await router.handle_command(
        chat_id=chat_id, command=command, args=args
    )
    if outcome.reply:
        await message.reply_text(outcome.reply)


async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forward plain text to Talk or the drafts queue."""
    message = update.effective_message
    if message is None or message.text is None:
        return
    router = _resolve_router(context)
    if router is None:
        await message.reply_text("⚠️ bridge unwired")
        return
    chat = message.chat
    chat_id = chat.id if chat is not None else 0
    sender = (
        message.from_user.username
        if message.from_user and message.from_user.username
        else None
    )
    outcome = await router.handle_message(
        chat_id=chat_id, sender=sender, text=message.text
    )
    if outcome.reply:
        await message.reply_text(outcome.reply)


def resolve_bot_token() -> str | None:
    """Read the configured bot token from the env (single source).

    Two names supported for back-compat: the canonical
    ``SELFFORK_TELEGRAM_BOT_TOKEN`` and the older ``TELEGRAM_BOT_TOKEN``.
    """
    for name in ("SELFFORK_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def resolve_run_mode() -> TelegramRunMode:
    """Polling unless ``SELFFORK_TELEGRAM_MODE=webhook`` is set explicitly."""
    raw = os.environ.get("SELFFORK_TELEGRAM_MODE", "").strip().lower()
    if raw == "webhook":
        return "webhook"
    return "polling"


def resolve_webhook_url() -> str | None:
    """Webhook target URL (``SELFFORK_TELEGRAM_WEBHOOK_URL`` or
    legacy ``TELEGRAM_WEBHOOK_URL``)."""
    for name in (
        "SELFFORK_TELEGRAM_WEBHOOK_URL",
        "TELEGRAM_WEBHOOK_URL",
    ):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None
