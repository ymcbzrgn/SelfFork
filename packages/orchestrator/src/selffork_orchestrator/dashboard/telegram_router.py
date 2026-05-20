"""FastAPI router for Telegram bridge status + setup + webhook + activity.

ADR-006 §4.7 wires Self Jr → operator (proactive destructive approval)
and operator → Self Jr (ad-hoc prompt) over Telegram. This router is
the **operator-facing** surface — Connections + Settings render from
its responses, and the inbound webhook lands here (for production
deployments).

S3 (ADR-007 §4) promoted the router from "env stub" to a real surface:

* ``/status`` reports the live bridge state (connected / not).
* ``/setup`` persists token + webhook URL to env (the Settings UI
  uses this for the first-run wizard; S4 moves persistence to YAML).
* ``/test`` actually calls :meth:`PtbTelegramBridge.notify` so the
  operator sees a Telegram message confirming the wiring.
* ``/webhook`` receives Telegram update POSTs in webhook mode and
  forwards them to the in-process :class:`PtbApplication`.
* ``/activity`` exposes the last N inbound + outbound events so the
  Connections card can render real "last activity" rather than a
  hardcoded "never".
"""

from __future__ import annotations

import os
from collections import deque
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from selffork_orchestrator.telegram.bridge import (
    NullTelegramBridge,
    TelegramBridge,
    TelegramMessage,
)


class TelegramStatusResponse(BaseModel):
    """Snapshot of the Telegram bridge wiring + recent activity."""

    state: Literal["not_configured", "connected", "errored"]
    bot_username: str | None = None
    webhook_url: str | None = None
    soft_confirm_window_hours: int = 4
    last_activity_at: str | None = None
    last_activity_summary: str | None = None
    detail: str | None = None
    mode: Literal["polling", "webhook"] | None = None


class TelegramSetupRequest(BaseModel):
    bot_token: str
    webhook_url: str | None = None


class TelegramTestRequest(BaseModel):
    body: str = "SelfFork test message — bridge is alive."


class TelegramActivityEntry(BaseModel):
    at: str
    direction: Literal["inbound", "outbound"]
    summary: str
    detail: str | None = None


class TelegramActivityResponse(BaseModel):
    inbound: list[TelegramActivityEntry]
    outbound: list[TelegramActivityEntry]


_ACTIVITY_RING_SIZE = 50


class TelegramActivityLog:
    """Tiny ring buffer for the Connections card "last activity" view.

    Lives next to the bridge in ``app.state`` so both the inbound
    PTB handlers and the outbound notify hook can append. Not
    persisted — losing the buffer across restarts is fine; the
    authoritative log is the Telegram chat itself.
    """

    def __init__(self, size: int = _ACTIVITY_RING_SIZE) -> None:
        self._inbound: deque[TelegramActivityEntry] = deque(maxlen=size)
        self._outbound: deque[TelegramActivityEntry] = deque(maxlen=size)

    def record_inbound(self, *, summary: str, detail: str | None = None) -> None:
        self._inbound.appendleft(
            TelegramActivityEntry(
                at=datetime.now(tz=UTC).isoformat(),
                direction="inbound",
                summary=summary,
                detail=detail,
            )
        )

    def record_outbound(self, *, summary: str, detail: str | None = None) -> None:
        self._outbound.appendleft(
            TelegramActivityEntry(
                at=datetime.now(tz=UTC).isoformat(),
                direction="outbound",
                summary=summary,
                detail=detail,
            )
        )

    def snapshot(self) -> TelegramActivityResponse:
        return TelegramActivityResponse(
            inbound=list(self._inbound),
            outbound=list(self._outbound),
        )

    def latest(self) -> TelegramActivityEntry | None:
        candidates: list[TelegramActivityEntry] = []
        if self._inbound:
            candidates.append(self._inbound[0])
        if self._outbound:
            candidates.append(self._outbound[0])
        if not candidates:
            return None
        return max(candidates, key=lambda e: e.at)


def build_telegram_router(
    *,
    bridge: TelegramBridge | None = None,
    application: Any = None,
    activity_log: TelegramActivityLog | None = None,
) -> APIRouter:
    """Construct the /api/telegram/* router.

    Args:
        bridge: live :class:`TelegramBridge` (``PtbTelegramBridge``
            in production, ``NullTelegramBridge`` for unconfigured
            deployments). ``None`` ⇒ ``NullTelegramBridge``.
        application: PTB :class:`Application` for inbound webhook
            forwarding. ``None`` keeps webhook 503 (no inbound).
        activity_log: optional ring buffer for the Connections card.
    """
    router = APIRouter(prefix="/api/telegram", tags=["telegram"])
    bridge = bridge or NullTelegramBridge()
    log = activity_log or TelegramActivityLog()

    def _resolve_mode() -> Literal["polling", "webhook"]:
        raw = os.environ.get("SELFFORK_TELEGRAM_MODE", "").strip().lower()
        return "webhook" if raw == "webhook" else "polling"

    def _resolve_webhook_url() -> str | None:
        for name in (
            "SELFFORK_TELEGRAM_WEBHOOK_URL",
            "TELEGRAM_WEBHOOK_URL",
        ):
            value = os.environ.get(name, "").strip()
            if value:
                return value
        return None

    def _resolve_bot_token() -> str:
        for name in ("SELFFORK_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
            value = os.environ.get(name, "").strip()
            if value:
                return value
        return ""

    @router.get("/status", response_model=TelegramStatusResponse)
    async def status() -> TelegramStatusResponse:
        bot_token = _resolve_bot_token()
        webhook_url = _resolve_webhook_url()
        soft_window = int(os.environ.get("SELFFORK_SOFT_CONFIRM_HOURS", "4"))
        mode = _resolve_mode()
        latest = log.latest()
        if not bot_token:
            return TelegramStatusResponse(
                state="not_configured",
                soft_confirm_window_hours=soft_window,
                detail="Set SELFFORK_TELEGRAM_BOT_TOKEN to enable the bridge.",
                mode=mode,
            )
        state: Literal["not_configured", "connected", "errored"] = (
            "connected"
            if not isinstance(bridge, NullTelegramBridge)
            else "errored"
        )
        return TelegramStatusResponse(
            state=state,
            bot_username=os.environ.get("TELEGRAM_BOT_USERNAME") or None,
            webhook_url=webhook_url,
            soft_confirm_window_hours=soft_window,
            last_activity_at=latest.at if latest else None,
            last_activity_summary=latest.summary if latest else None,
            detail=(
                None
                if not isinstance(bridge, NullTelegramBridge)
                else "Bridge is NullTelegramBridge (token set but PTB not initialised)."
            ),
            mode=mode,
        )

    @router.post("/setup", response_model=TelegramStatusResponse)
    async def setup(req: TelegramSetupRequest) -> TelegramStatusResponse:
        if not req.bot_token.strip():
            raise HTTPException(
                status_code=400, detail="bot_token must not be empty"
            )
        os.environ["SELFFORK_TELEGRAM_BOT_TOKEN"] = req.bot_token.strip()
        if req.webhook_url:
            os.environ["SELFFORK_TELEGRAM_WEBHOOK_URL"] = req.webhook_url.strip()
        return await status()

    @router.post("/test")
    async def send_test(req: TelegramTestRequest) -> dict[str, str]:
        if isinstance(bridge, NullTelegramBridge):
            raise HTTPException(
                status_code=503,
                detail="Telegram bridge is NullTelegramBridge — set a bot token and restart.",
            )
        message = TelegramMessage(
            level="info",
            text=req.body,
            session_id="dashboard-test",
            project_slug=None,
        )
        attempt = await bridge.notify(message)
        log.record_outbound(
            summary="Test message",
            detail=req.body if attempt.delivered else (attempt.reason or "unknown"),
        )
        if not attempt.delivered:
            raise HTTPException(
                status_code=502,
                detail=attempt.reason or "Telegram delivery failed.",
            )
        return {"status": "delivered", "chat_id": str(attempt.chat_id or "")}

    @router.get("/activity", response_model=TelegramActivityResponse)
    async def activity() -> TelegramActivityResponse:
        return log.snapshot()

    @router.post("/webhook")
    async def webhook(request: Request) -> dict[str, str]:
        """Receive Telegram update POSTs (webhook mode only).

        Telegram's bot platform POSTs JSON-encoded ``Update`` objects to
        the URL the operator registered via ``setWebhook``. We parse,
        verify the application is wired, and hand off to PTB.
        """
        if application is None:
            raise HTTPException(
                status_code=503,
                detail="Telegram inbound application not initialised.",
            )
        # S3 audit fix #2 — webhook secret-token check. When
        # SELFFORK_TELEGRAM_WEBHOOK_SECRET is set the operator's
        # setWebhook call must include it; every inbound POST then
        # carries X-Telegram-Bot-Api-Secret-Token. Without this gate
        # anyone with the webhook URL can spoof callback_query
        # updates and approve destructive actions.
        expected_secret = os.environ.get(
            "SELFFORK_TELEGRAM_WEBHOOK_SECRET", ""
        ).strip()
        if expected_secret:
            provided = request.headers.get(
                "X-Telegram-Bot-Api-Secret-Token", ""
            )
            if provided != expected_secret:
                raise HTTPException(
                    status_code=401,
                    detail="invalid webhook secret token",
                )
        from telegram import Update  # local import to keep router cheap

        payload = await request.json()
        try:
            update = Update.de_json(payload, application.bot)  # type: ignore[arg-type]
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid Telegram update: {exc}"
            ) from exc
        if update is None:
            raise HTTPException(
                status_code=400, detail="empty Telegram update"
            )
        log.record_inbound(
            summary=_summarise_inbound(update),
            detail=None,
        )
        await application.process_update(update)
        return {"status": "ok"}

    return router


def _summarise_inbound(update: Any) -> str:
    """One-line summary of a Telegram update for the activity log."""
    if getattr(update, "callback_query", None):
        data = getattr(update.callback_query, "data", "")
        return f"callback: {data}"
    message = getattr(update, "effective_message", None)
    if message is not None:
        text = getattr(message, "text", "") or ""
        return f"message: {text[:80]}"
    return "update (unsupported type)"


def attach_outbound_recorder(
    bridge: TelegramBridge, log: TelegramActivityLog
) -> TelegramBridge:
    """Wrap ``bridge`` so every successful notify hits the activity log.

    Used by the dashboard lifespan to surface outbound destructive
    notifications in the Connections card without modifying the bridge
    class itself.
    """

    class _Wrapping(TelegramBridge):
        async def notify(self, message: TelegramMessage):
            attempt = await bridge.notify(message)
            if attempt.delivered:
                log.record_outbound(
                    summary=message.text.splitlines()[0][:80]
                    if message.text
                    else "(empty)",
                    detail=f"level={message.level} session={message.session_id}",
                )
            return attempt

    return _Wrapping()


__all__ = [
    "TelegramActivityEntry",
    "TelegramActivityLog",
    "TelegramActivityResponse",
    "TelegramSetupRequest",
    "TelegramStatusResponse",
    "TelegramTestRequest",
    "attach_outbound_recorder",
    "build_telegram_router",
]
