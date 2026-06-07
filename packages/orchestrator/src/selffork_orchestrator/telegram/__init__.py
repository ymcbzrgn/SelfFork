"""Telegram bridge — operator notifications + inbound commands.

Order 5 scaffold (this module): defines the bridge interface, a no-op
implementation, the operator allowlist (``~/.selffork/operators.json``),
and the persistent pending-messages inbox (``~/.selffork/telegram-inbox.sqlite``).

Order 9 wires the real ``python-telegram-bot v22.7`` implementation as a
concrete :class:`TelegramBridge` subclass — long-polling with
``AIORateLimiter`` and ``JobQueue``, inline keyboards for confirm/cancel
flows, and ``ntfy.sh`` fallback.

Why ABC + Null pattern: the Jr autopilot's ``notify_telegram`` tool emits
intent into the audit log regardless of whether PTB is installed; the
orchestrator round-loop drains the audit log and routes through whatever
bridge is wired (Null in M3-M5 dev, PTB in production).
"""

from __future__ import annotations

from selffork_orchestrator.telegram.allowlist import (
    AllowList,
    AllowListConfig,
    default_allowlist_path,
)
from selffork_orchestrator.telegram.bridge import (
    DeliveryAttempt,
    NullTelegramBridge,
    TelegramBridge,
    TelegramMessage,
)
from selffork_orchestrator.telegram.drafts import (
    TelegramDraft,
    TelegramDraftStore,
    default_drafts_path,
)
from selffork_orchestrator.telegram.inbound_router import (
    CallbackOutcome,
    CommandOutcome,
    InboundRouter,
    MessageOutcome,
    PauseSignal,
)
from selffork_orchestrator.telegram.inbox import (
    PendingMessage,
    TelegramInbox,
    default_inbox_path,
)
from selffork_orchestrator.telegram.ptb import PtbTelegramBridge

__all__ = [
    "AllowList",
    "AllowListConfig",
    "CallbackOutcome",
    "CommandOutcome",
    "DeliveryAttempt",
    "InboundRouter",
    "MessageOutcome",
    "NullTelegramBridge",
    "PauseSignal",
    "PendingMessage",
    "PtbTelegramBridge",
    "TelegramBridge",
    "TelegramDraft",
    "TelegramDraftStore",
    "TelegramInbox",
    "TelegramMessage",
    "default_allowlist_path",
    "default_drafts_path",
    "default_inbox_path",
]
