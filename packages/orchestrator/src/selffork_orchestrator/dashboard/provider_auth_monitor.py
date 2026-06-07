"""Provider auth expiry monitor + Telegram alert hook (S5 — ADR-007 §4).

Operator direktifi 2026-05-23:

    "auth kendi kendine çıktıysa telegramdan giriş yap auth kapanmış
     cliden çıkılmış falan diye uyarmamız lazım"

CLI-native sign-in (operator runs ``<cli> login`` in the terminal)
means SelfFork doesn't orchestrate browser-auth itself, but it does
need to **notice** when a CLI's session has expired and surface that
to the operator — otherwise Self Jr keeps banging on a dead session
and the operator finds out hours later from the audit log.

This module owns the alert side. Any caller (snapper layer detecting
``401`` / ``403``, CLI invocation wrapper catching an
``authentication_required`` error, the Connections card refresh
button) reaches us through one entry point:

    await monitor.notify_auth_expired(provider, reason)

We dedup with a per-provider cooldown window so a hammering snapper
doesn't spam the operator's chat, then send a single Telegram message
with the exact terminal command to re-authenticate that CLI. The
``ProviderRegistry`` is also flipped to record the expiry so the
Connections card reflects it on the next poll.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

from selffork_orchestrator.telegram.bridge import (
    NullTelegramBridge,
    TelegramBridge,
    TelegramMessage,
)

_log = logging.getLogger(__name__)


# CLI re-authentication command per canonical provider name. Keep this
# in lockstep with the ``Provider`` enum in ``provider_router``.
CLI_LOGIN_COMMANDS: Final[dict[str, str]] = {
    "claude_pro": "claude /login",
    "codex": "codex login",
    "gemini": "gemini auth login",
    "opencode": "opencode auth login",
    "mmx": "minimax-cli login",
}


DEFAULT_COOLDOWN_MINUTES: Final[int] = 5


@dataclass
class ProviderAuthAlert:
    """One alert that has been (or would have been) sent to Telegram."""

    provider: str
    reason: str
    alerted_at: datetime
    delivered: bool
    cooldown_skipped: bool = False


@dataclass
class ProviderAuthMonitor:
    """Notifies the operator via Telegram when a provider auth expires.

    Construction is cheap (no I/O); the actual Telegram send happens
    only on :meth:`notify_auth_expired`. The dashboard wires this in
    once at boot and shares the instance via ``app.state``.
    """

    bridge: TelegramBridge | None = None
    cooldown: timedelta = field(default_factory=lambda: timedelta(minutes=DEFAULT_COOLDOWN_MINUTES))
    _last_alert: dict[str, datetime] = field(default_factory=dict, init=False)
    _history: list[ProviderAuthAlert] = field(default_factory=list, init=False)

    async def notify_auth_expired(
        self,
        provider: str,
        reason: str = "auth expired",
    ) -> ProviderAuthAlert:
        """Send a Telegram alert (subject to cooldown).

        Returns a :class:`ProviderAuthAlert` describing the outcome.
        ``cooldown_skipped=True`` means we suppressed the alert
        because a previous one fired within the cooldown window;
        ``delivered=False`` means the Telegram round-trip failed
        (bridge unconfigured or transport error).
        """
        now = datetime.now(UTC)
        last = self._last_alert.get(provider)
        if last is not None and (now - last) < self.cooldown:
            alert = ProviderAuthAlert(
                provider=provider,
                reason=reason,
                alerted_at=now,
                delivered=False,
                cooldown_skipped=True,
            )
            self._history.append(alert)
            _log.info(
                "provider_auth_alert_cooldown_skipped",
                extra={"provider": provider, "reason": reason},
            )
            return alert

        self._last_alert[provider] = now
        delivered = False
        if self.bridge is not None and not isinstance(self.bridge, NullTelegramBridge):
            text = _format_alert(provider, reason)
            try:
                attempt = await self.bridge.notify(
                    TelegramMessage(
                        level="warn",
                        text=text,
                        session_id="provider-auth-monitor",
                        project_slug=None,
                    )
                )
                delivered = bool(getattr(attempt, "delivered", False))
            except Exception as exc:
                _log.warning(
                    "provider_auth_alert_send_failed",
                    extra={
                        "provider": provider,
                        "reason": reason,
                        "error": str(exc),
                    },
                )
                delivered = False
        else:
            _log.info(
                "provider_auth_alert_bridge_unconfigured",
                extra={"provider": provider, "reason": reason},
            )

        alert = ProviderAuthAlert(
            provider=provider,
            reason=reason,
            alerted_at=now,
            delivered=delivered,
        )
        self._history.append(alert)
        return alert

    def history(self) -> list[ProviderAuthAlert]:
        """Return the in-memory alert history (most-recent last)."""
        return list(self._history)


def _format_alert(provider: str, reason: str) -> str:
    """Compose the Telegram message body for an auth-expired alert.

    Audit-god MEDIUM #4 (2026-05-23): the PTB bridge HTML-escapes the
    entire message body before sending, so embedded ``<b>`` / ``<code>``
    tags would render literally in the operator's chat. We use plain
    text + Markdown-ish backticks; the bridge passes both through
    unchanged and Telegram's HTML parse_mode renders backticks as
    plain characters. Operator gets a clean readable nudge.
    """
    cmd = CLI_LOGIN_COMMANDS.get(provider, f"{provider} login")
    return (
        f"🔐 Auth expired: {provider}\n"
        f"Reason: {reason}\n"
        "\n"
        "Run this in your terminal to re-authenticate:\n"
        f"  {cmd}"
    )
