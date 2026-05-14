"""TelegramBridge ABC + null implementation.

The bridge mediates between the orchestrator round-loop and the operator's
Telegram chat. Real implementations (Order 9) wrap python-telegram-bot
v22.7. The :class:`NullTelegramBridge` is the default when PTB is not
installed or Telegram is intentionally disabled — it records intent so
M3-M6 audit logs (M7 fine-tune dataset) still capture Yamaç-style
notify decisions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

__all__ = [
    "DeliveryAttempt",
    "NotifyLevel",
    "NullTelegramBridge",
    "TelegramBridge",
    "TelegramMessage",
]


NotifyLevel = Literal["info", "warn", "crit"]


@dataclass(frozen=True, slots=True)
class TelegramMessage:
    """One outbound message destined for the operator's chat."""

    level: NotifyLevel
    text: str
    session_id: str
    project_slug: str | None = None


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    """The result of a :meth:`TelegramBridge.notify` call."""

    delivered: bool
    reason: str | None = None
    chat_id: int | None = None
    sent_at: datetime | None = None


class TelegramBridge(ABC):
    """Abstract bridge between orchestrator and operator Telegram."""

    @abstractmethod
    async def notify(self, message: TelegramMessage) -> DeliveryAttempt:
        """Push ``message`` to the operator. Returns the delivery outcome.

        Implementations MUST NOT raise on transient delivery failure —
        return :class:`DeliveryAttempt` with ``delivered=False`` and a
        ``reason`` so callers (round-loop) can decide whether to retry
        or fall back to ntfy.sh / web UI.
        """


class NullTelegramBridge(TelegramBridge):
    """No-op bridge — does not contact Telegram at all.

    Default in M3-M5 (and CI). Always returns ``delivered=False`` with a
    ``reason`` indicating the bridge is not wired.
    """

    async def notify(self, message: TelegramMessage) -> DeliveryAttempt:
        return DeliveryAttempt(
            delivered=False,
            reason=(
                "NullTelegramBridge — Telegram bridge not wired. "
                "Order 9 ships the python-telegram-bot v22.7 implementation."
            ),
            sent_at=datetime.now(tz=UTC),
        )
