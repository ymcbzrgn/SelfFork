"""FastAPI router for Telegram bridge status + setup + webhook + activity.

ADR-006 §4.7 wires Self Jr → operator (proactive destructive approval)
and operator → Self Jr (ad-hoc prompt) over Telegram. This router is
the **operator-facing** surface — Connections + Settings render from
its responses, and the inbound webhook lands here (for production
deployments).

S3 (ADR-007 §4) promoted the router from "env stub" to a real surface;
S5 (this revision) persists the operator wizard's payload to YAML
(``~/.selffork/settings/telegram.yaml``) and actually calls Telegram's
``setWebhook`` API when the operator picks webhook mode:

* ``/status`` reports the live bridge state. YAML > env > defaults.
* ``/setup`` writes the wizard payload to YAML and (if webhook mode)
  registers the public URL with Telegram. **Effect on next dashboard
  restart** — the bridge + inbound application are constructed at
  ``build_app`` time, so the new token does not flip the live bridge.
* ``/test`` actually calls :meth:`PtbTelegramBridge.notify` so the
  operator sees a Telegram message confirming the wiring.
* ``/webhook`` receives Telegram update POSTs in webhook mode and
  forwards them to the in-process :class:`PtbApplication`.
* ``/activity`` exposes the last N inbound + outbound events so the
  Connections card can render real "last activity" rather than a
  hardcoded "never".
"""

from __future__ import annotations

import logging
import os
from collections import deque
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from selffork_orchestrator.dashboard.settings import (
    TelegramConfig,
    YamlSettingsStore,
    default_telegram_store,
    resolve_telegram_config,
)
from selffork_orchestrator.telegram.allowlist import (
    default_allowlist_path,
)
from selffork_orchestrator.telegram.bridge import (
    NullTelegramBridge,
    TelegramBridge,
    TelegramMessage,
)

_log = logging.getLogger(__name__)


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
    """First-run wizard payload from the Connections card.

    S5 (ADR-007 §4) — the wizard persists to
    ``~/.selffork/settings/telegram.yaml`` and, when ``mode='webhook'``,
    registers ``webhook_url`` with Telegram's Bot API before returning.
    Bot token is the only required field; the rest carry sane defaults
    matching :class:`TelegramConfig`.
    """

    model_config = ConfigDict(extra="forbid")

    bot_token: str
    chat_id: str = ""
    mode: Literal["polling", "webhook"] = "polling"
    webhook_url: str = ""
    webhook_secret: str = ""
    soft_confirm_window_hours: int = Field(default=4, ge=1, le=72)


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
    store: YamlSettingsStore[TelegramConfig] | None = None,
) -> APIRouter:
    """Construct the /api/telegram/* router.

    Args:
        bridge: live :class:`TelegramBridge` (``PtbTelegramBridge``
            in production, ``NullTelegramBridge`` for unconfigured
            deployments). ``None`` ⇒ ``NullTelegramBridge``.
        application: PTB :class:`Application` for inbound webhook
            forwarding. ``None`` keeps webhook 503 (no inbound).
        activity_log: optional ring buffer for the Connections card.
        store: YAML store for :class:`TelegramConfig`. ``None`` falls
            back to ``~/.selffork/settings/telegram.yaml`` (S5).
    """
    router = APIRouter(prefix="/api/telegram", tags=["telegram"])
    bridge = bridge or NullTelegramBridge()
    log = activity_log or TelegramActivityLog()
    telegram_store = store or default_telegram_store()

    @router.get("/status", response_model=TelegramStatusResponse)
    async def status() -> TelegramStatusResponse:
        cfg = resolve_telegram_config(telegram_store)
        latest = log.latest()
        if not cfg.bot_token:
            return TelegramStatusResponse(
                state="not_configured",
                soft_confirm_window_hours=cfg.soft_confirm_window_hours,
                detail=(
                    "Open the Connections card or PUT "
                    "/api/telegram/setup to register a bot token."
                ),
                mode=cfg.mode,
            )
        state: Literal["not_configured", "connected", "errored"] = (
            "connected"
            if not isinstance(bridge, NullTelegramBridge)
            else "errored"
        )
        return TelegramStatusResponse(
            state=state,
            bot_username=os.environ.get("TELEGRAM_BOT_USERNAME") or None,
            webhook_url=cfg.webhook_url or None,
            soft_confirm_window_hours=cfg.soft_confirm_window_hours,
            last_activity_at=latest.at if latest else None,
            last_activity_summary=latest.summary if latest else None,
            detail=(
                None
                if not isinstance(bridge, NullTelegramBridge)
                else (
                    "Token configured but the bridge is still "
                    "NullTelegramBridge. Restart the dashboard so PTB "
                    "picks up the new YAML."
                )
            ),
            mode=cfg.mode,
        )

    @router.post("/setup", response_model=TelegramStatusResponse)
    async def setup(req: TelegramSetupRequest) -> TelegramStatusResponse:
        bot_token = req.bot_token.strip()
        if not bot_token:
            raise HTTPException(
                status_code=400, detail="bot_token must not be empty"
            )
        webhook_url = req.webhook_url.strip()
        if req.mode == "webhook" and not webhook_url:
            raise HTTPException(
                status_code=400,
                detail=(
                    "webhook_url is required when mode='webhook'; "
                    "Telegram setWebhook needs the public HTTPS URL."
                ),
            )
        config = TelegramConfig(
            bot_token=bot_token,
            chat_id=req.chat_id.strip(),
            mode=req.mode,
            webhook_url=webhook_url,
            webhook_secret=req.webhook_secret.strip(),
            soft_confirm_window_hours=req.soft_confirm_window_hours,
        )
        telegram_store.write(config)
        # S5 audit-god HIGH #3 fix: the wizard's chat_id must feed
        # into the allowlist (operators.json), otherwise the bridge
        # comes up "connected" but every notify is dropped with
        # "empty operator allowlist". Merge instead of replace so
        # multi-operator deployments aren't clobbered.
        if config.chat_id:
            _merge_chat_id_into_allowlist(config.chat_id)
        if config.mode == "webhook":
            try:
                await _register_telegram_webhook(
                    bot_token=config.bot_token,
                    webhook_url=config.webhook_url,
                    webhook_secret=config.webhook_secret,
                )
            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Telegram setWebhook call failed: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                ) from exc
        log.record_outbound(
            summary="Setup wizard applied",
            detail=(
                f"mode={config.mode} "
                + (
                    f"webhook_url={config.webhook_url}"
                    if config.webhook_url
                    else "no_webhook"
                )
            ),
        )
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
        # S3 audit fix #2 + S5 audit-god HIGH #2 — webhook secret-token
        # check. The operator's setWebhook call (S5 wizard or env)
        # tells Telegram to attach X-Telegram-Bot-Api-Secret-Token on
        # every push; without verification anyone reaching the webhook
        # URL can spoof callback_query updates and approve destructive
        # actions. We resolve the secret via the SAME resolver as
        # /setup so YAML-only operators are guarded too (env wins when
        # explicitly set, falls back to the YAML config otherwise).
        resolved_cfg = resolve_telegram_config(telegram_store)
        expected_secret = (resolved_cfg.webhook_secret or "").strip()
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


def _merge_chat_id_into_allowlist(chat_id_text: str) -> None:
    """Merge ``chat_id_text`` into ``~/.selffork/operators.json``.

    The wizard collects a string (operators copy-paste it from Telegram
    chat info), so we parse defensively: non-integer entries are
    skipped silently — the operator can still hand-edit the file.
    The merge is atomic (temp+rename) so concurrent
    ``AllowList.load()`` always sees a coherent file.

    Audit-god HIGH #3 (2026-05-23): without this, the wizard appears
    to ask for everything but the bridge actually requires this file.
    """
    import json

    try:
        chat_id_int = int(chat_id_text.strip())
    except (TypeError, ValueError):
        _log.info(
            "telegram_setup_chat_id_not_numeric_skipped",
            extra={"value": chat_id_text},
        )
        return
    path = default_allowlist_path()
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (OSError, json.JSONDecodeError):
            existing = {}
    raw_ids = existing.get("chat_ids")
    ids: list[int] = []
    if isinstance(raw_ids, list):
        for x in raw_ids:
            if isinstance(x, int) and not isinstance(x, bool):
                ids.append(x)
    if chat_id_int not in ids:
        ids.append(chat_id_int)
    existing["chat_ids"] = ids
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    temp.replace(path)


async def _register_telegram_webhook(
    *,
    bot_token: str,
    webhook_url: str,
    webhook_secret: str,
) -> dict[str, Any]:
    """Call Telegram's ``setWebhook`` API.

    Wired by ``/api/telegram/setup`` when the operator picks webhook
    mode. Telegram will reject the request if the URL isn't HTTPS
    on a public port, so we surface its error verbatim — the
    Connections card displays it.
    """
    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    payload: dict[str, Any] = {"url": webhook_url}
    if webhook_secret:
        payload["secret_token"] = webhook_secret
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
    if resp.status_code != 200:
        raise httpx.HTTPStatusError(
            f"setWebhook returned HTTP {resp.status_code}: {resp.text}",
            request=resp.request,
            response=resp,
        )
    raw = resp.json()
    if not isinstance(raw, dict):
        raise httpx.HTTPStatusError(
            f"setWebhook returned non-object body: {raw!r}",
            request=resp.request,
            response=resp,
        )
    body: dict[str, Any] = raw
    if not body.get("ok"):
        # Telegram returns 200 + ok=false for application-level errors
        # (bad URL, mismatched token, etc). Surface as transport error.
        raise httpx.HTTPStatusError(
            f"setWebhook ok=false: {body!r}",
            request=resp.request,
            response=resp,
        )
    return body


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
