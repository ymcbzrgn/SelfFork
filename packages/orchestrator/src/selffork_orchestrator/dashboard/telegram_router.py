"""FastAPI router for Telegram bridge status + setup.

ADR-006 §4.7 wires Self Jr → operator (proactive destructive
approval) and operator → Self Jr (ad-hoc prompt) over Telegram. The
underlying ``PtbTelegramBridge`` already ships (commit b57a765); this
router exposes the **operator-facing** surface so the cockpit
Connections + Settings pages can configure the bot token, view
delivery status, and send test messages.
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


class TelegramStatusResponse(BaseModel):
    """Snapshot of the Telegram bridge wiring + recent activity."""

    state: Literal["not_configured", "connected", "errored"]
    bot_username: str | None = None
    webhook_url: str | None = None
    soft_confirm_window_hours: int = 4
    last_activity_at: str | None = None
    last_activity_summary: str | None = None
    detail: str | None = None


class TelegramSetupRequest(BaseModel):
    bot_token: str
    webhook_url: str


class TelegramTestRequest(BaseModel):
    body: str = "SelfFork test message — bridge is alive."


def build_telegram_router() -> APIRouter:
    """Construct the /api/telegram/* router.

    MV: reads bot config from env (``TELEGRAM_BOT_TOKEN``,
    ``TELEGRAM_WEBHOOK_URL``); a runtime-mutable in-memory shim handles
    setup posts so the Settings UI can update without restart. The
    real persisted config + PtbTelegramBridge lifecycle land in M6.6.
    """
    router = APIRouter(prefix="/api/telegram", tags=["telegram"])

    @router.get("/status", response_model=TelegramStatusResponse)
    async def status() -> TelegramStatusResponse:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        webhook_url = os.environ.get("TELEGRAM_WEBHOOK_URL", "").strip()
        soft_window = int(os.environ.get("SELFFORK_SOFT_CONFIRM_HOURS", "4"))
        if not bot_token:
            return TelegramStatusResponse(
                state="not_configured",
                soft_confirm_window_hours=soft_window,
                detail="Set TELEGRAM_BOT_TOKEN to enable the bridge.",
            )
        return TelegramStatusResponse(
            state="connected",
            bot_username=os.environ.get("TELEGRAM_BOT_USERNAME") or None,
            webhook_url=webhook_url or None,
            soft_confirm_window_hours=soft_window,
        )

    @router.post("/setup", response_model=TelegramStatusResponse)
    async def setup(req: TelegramSetupRequest) -> TelegramStatusResponse:
        """Register a bot token + webhook URL.

        MV writes to process env (lost on restart). M6.6 persists to
        ``~/.selffork/telegram.yaml`` and bounces the bridge.
        """
        if not req.bot_token.strip():
            raise HTTPException(
                status_code=400, detail="bot_token must not be empty"
            )
        os.environ["TELEGRAM_BOT_TOKEN"] = req.bot_token.strip()
        os.environ["TELEGRAM_WEBHOOK_URL"] = req.webhook_url.strip()
        return TelegramStatusResponse(
            state="connected",
            webhook_url=req.webhook_url.strip() or None,
            soft_confirm_window_hours=int(
                os.environ.get("SELFFORK_SOFT_CONFIRM_HOURS", "4")
            ),
        )

    @router.post("/test")
    async def send_test(_req: TelegramTestRequest) -> dict[str, str]:
        """Send a test message via the bridge.

        MV always 503s with "bridge not connected" — wiring lives in
        M6.6 once ``PtbTelegramBridge`` is instantiated on startup.
        """
        if not os.environ.get("TELEGRAM_BOT_TOKEN"):
            raise HTTPException(
                status_code=503,
                detail="Telegram bridge is not configured.",
            )
        # PtbTelegramBridge.notify() integration → M6.6.
        raise HTTPException(
            status_code=501,
            detail="Test-message endpoint wires in M6.6.",
        )

    return router
