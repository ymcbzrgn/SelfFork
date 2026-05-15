"""``python-telegram-bot`` v22.7 concrete :class:`TelegramBridge`.

Order 9 close-out: replaces the :class:`NullTelegramBridge` default with
a real PTB-driven push-only bridge for the operator's chat. Inbound
command handling (``/cancel``, ``/p <slug> <msg>``) is wired separately
in a follow-up patch; this class focuses on outbound notifications
emitted by the autopilot ``notify_telegram`` tool.

Auth-only kuralı: the bot token is read from the ``SELFFORK_TELEGRAM_BOT_TOKEN``
environment variable. No SelfFork-side token is hardcoded; if the env
var is unset, callers should keep using :class:`NullTelegramBridge`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Final

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

from selffork_orchestrator.telegram.allowlist import AllowList
from selffork_orchestrator.telegram.bridge import (
    DeliveryAttempt,
    TelegramBridge,
    TelegramMessage,
)

__all__ = ["PtbTelegramBridge"]


# Telegram message-text limit (UTF-16 codeunits per the Bot API).
_MAX_MESSAGE_CHARS: Final[int] = 4000  # leave headroom under the 4096 limit


class PtbTelegramBridge(TelegramBridge):
    """Push-only bridge to the operator's Telegram chat via PTB v22.7.

    Args:
        bot_token: Bot API token. **Required** — caller falls back to
            :class:`NullTelegramBridge` when no token is configured.
        allowlist: Operator chat-id allowlist. Each ``notify`` call
            broadcasts to every allowed chat (typically just one — the
            operator's DM). Empty allowlist → ``DeliveryAttempt`` with
            ``delivered=False`` and a clear reason.
        connection_timeout: HTTP connect timeout (s). Default 5s.
        read_timeout: HTTP read timeout (s). Default 10s.
    """

    def __init__(
        self,
        *,
        bot_token: str,
        allowlist: AllowList,
        connection_timeout: float = 5.0,
        read_timeout: float = 10.0,
    ) -> None:
        if not bot_token:
            raise ValueError("PtbTelegramBridge requires a non-empty bot_token.")
        self._allowlist = allowlist
        request = HTTPXRequest(
            connection_pool_size=4,
            connect_timeout=connection_timeout,
            read_timeout=read_timeout,
        )
        self._bot = Bot(token=bot_token, request=request)

    async def notify(self, message: TelegramMessage) -> DeliveryAttempt:
        if not self._allowlist.chat_ids:
            return DeliveryAttempt(
                delivered=False,
                reason=(
                    "PtbTelegramBridge: empty operator allowlist; nothing "
                    "to deliver. Populate ~/.selffork/operators.json."
                ),
                sent_at=datetime.now(tz=UTC),
            )

        text = _format_message(message)
        sent_at = datetime.now(tz=UTC)
        last_error: str | None = None
        delivered_chat_id: int | None = None

        # Single-operator setup is the common case (chat_ids holds 1
        # entry). Iterate so we still work for future multi-operator
        # deployments; first success wins for the returned chat_id.
        for chat_id in sorted(self._allowlist.chat_ids):
            try:
                await self._send_one(chat_id=chat_id, text=text)
            except TelegramError as exc:
                last_error = f"chat_id={chat_id}: {exc}"
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = f"chat_id={chat_id}: unexpected: {exc}"
                continue
            if delivered_chat_id is None:
                delivered_chat_id = chat_id

        if delivered_chat_id is None:
            return DeliveryAttempt(
                delivered=False,
                reason=last_error or "PtbTelegramBridge: no chat reachable",
                sent_at=sent_at,
            )
        return DeliveryAttempt(
            delivered=True,
            reason=last_error,  # populated only when SOME chat failed
            chat_id=delivered_chat_id,
            sent_at=sent_at,
        )

    async def _send_one(self, *, chat_id: int, text: str) -> None:
        """Single-chat HTML send. Extracted as a method so tests can
        replace the network-side without monkey-patching PTB's frozen
        ``Bot.send_message`` attribute.
        """
        await self._bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


_LEVEL_PREFIX = {
    "info": "ℹ️",  # noqa: RUF001 — INFORMATION SOURCE + VS16
    "warn": "⚠️",  # WARNING SIGN + VS16
    "crit": "\U0001f6a8",  # POLICE CARS REVOLVING LIGHT
}


def _format_message(message: TelegramMessage) -> str:
    """Render a TelegramMessage as HTML-safe text within Telegram limits."""
    icon = _LEVEL_PREFIX.get(message.level, "•")
    project = (
        f" · <code>{_html_escape(message.project_slug)}</code>" if message.project_slug else ""
    )
    head = (
        f"{icon} <b>SelfFork</b> [{_html_escape(message.level)}]"
        f"{project} · <code>{_html_escape(message.session_id)}</code>"
    )
    body = _html_escape(message.text)
    text = f"{head}\n\n{body}"
    if len(text) > _MAX_MESSAGE_CHARS:
        text = text[: _MAX_MESSAGE_CHARS - 18] + "\n\n[truncated]"
    return text


def _html_escape(value: str) -> str:
    """Minimal Telegram HTML escape — only the documented entities."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
