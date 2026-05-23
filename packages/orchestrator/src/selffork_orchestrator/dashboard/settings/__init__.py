"""Operator-driven settings persistence (ADR-007 §4 S4).

Per-topic YAML stores under ``~/.selffork/settings/`` — one file per
concern so atomic writes never clobber unrelated operator state. The
pattern mirrors
:class:`selffork_orchestrator.heartbeat.autonomy.AutonomyStore`:
read_or_default + atomic temp+rename write.

* ``model-endpoint.yaml`` — Self Jr Talk endpoint URL / protocol /
  model / auth.
* ``destructive-whitelist.yaml`` — operator override of bundled
  ADR-006 §4.5 whitelist (falls back to bundled default when absent).
* ``codexbar.yaml`` — CodexBar sidecar version pin + auto-update
  toggle + binary path override.

Vision settings keep their pre-S4 home (``selffork.yaml`` ``vision:``
key) via :mod:`selffork_orchestrator.dashboard.settings_router` —
that surface predates S4 and stays separate (operator decision
2026-05-23: ``/cockpit/settings/vision`` separate page).
"""

from __future__ import annotations

from pathlib import Path

from selffork_orchestrator.dashboard.settings.destructive import (
    DEFAULT_DESTRUCTIVE_OVERRIDE_PATH,
    destructive_whitelist_source,
    load_effective_destructive_whitelist,
    resolve_destructive_whitelist_path,
)
from selffork_orchestrator.dashboard.settings.schemas import (
    CodexBarUserConfig,
    ModelEndpointConfig,
    ModelEndpointHealth,
    TelegramConfig,
)
from selffork_orchestrator.dashboard.settings.store import YamlSettingsStore

__all__ = [
    "DEFAULT_DESTRUCTIVE_OVERRIDE_PATH",
    "CodexBarUserConfig",
    "ModelEndpointConfig",
    "ModelEndpointHealth",
    "TelegramConfig",
    "YamlSettingsStore",
    "default_codexbar_user_store",
    "default_model_endpoint_store",
    "default_telegram_store",
    "destructive_whitelist_source",
    "load_effective_destructive_whitelist",
    "resolve_destructive_whitelist_path",
    "resolve_telegram_config",
]


def _default_settings_dir() -> Path:
    return Path("~/.selffork/settings").expanduser()


def default_model_endpoint_store() -> YamlSettingsStore[ModelEndpointConfig]:
    """Factory for the default ``~/.selffork/settings/model-endpoint.yaml`` store."""
    return YamlSettingsStore(
        path=_default_settings_dir() / "model-endpoint.yaml",
        schema=ModelEndpointConfig,
        default_factory=ModelEndpointConfig,
    )


def default_codexbar_user_store() -> YamlSettingsStore[CodexBarUserConfig]:
    """Factory for the default ``~/.selffork/settings/codexbar.yaml`` store."""
    return YamlSettingsStore(
        path=_default_settings_dir() / "codexbar.yaml",
        schema=CodexBarUserConfig,
        default_factory=CodexBarUserConfig,
    )


def default_telegram_store() -> YamlSettingsStore[TelegramConfig]:
    """Factory for the default ``~/.selffork/settings/telegram.yaml`` store."""
    return YamlSettingsStore(
        path=_default_settings_dir() / "telegram.yaml",
        schema=TelegramConfig,
        default_factory=TelegramConfig,
    )


def resolve_telegram_config(
    store: YamlSettingsStore[TelegramConfig] | None = None,
) -> TelegramConfig:
    """Return the effective Telegram config (YAML > env > defaults).

    The S3 telegram_router resolved bot_token / webhook_url / mode
    from env directly. S5 layers a YAML store on top: when the
    operator has used the Connections setup wizard, its YAML wins;
    otherwise env vars stay authoritative (CI fixtures, server
    self-host startup scripts).
    """
    import os

    effective_store = store or default_telegram_store()
    persisted = effective_store.read()
    base = persisted if persisted is not None else TelegramConfig()

    # Env fallback only when the YAML field is empty / default.
    bot_token = base.bot_token
    if not bot_token:
        for name in ("SELFFORK_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
            value = os.environ.get(name, "").strip()
            if value:
                bot_token = value
                break
    webhook_url = base.webhook_url
    if not webhook_url:
        for name in (
            "SELFFORK_TELEGRAM_WEBHOOK_URL",
            "TELEGRAM_WEBHOOK_URL",
        ):
            value = os.environ.get(name, "").strip()
            if value:
                webhook_url = value
                break
    webhook_secret = base.webhook_secret
    if not webhook_secret:
        env_secret = os.environ.get(
            "SELFFORK_TELEGRAM_WEBHOOK_SECRET", ""
        ).strip()
        if env_secret:
            webhook_secret = env_secret
    mode = base.mode
    if persisted is None:
        env_mode = (
            os.environ.get("SELFFORK_TELEGRAM_MODE", "").strip().lower()
        )
        if env_mode == "webhook":
            mode = "webhook"
    soft_window = base.soft_confirm_window_hours
    if persisted is None:
        import contextlib

        raw = os.environ.get("SELFFORK_SOFT_CONFIRM_HOURS", "").strip()
        if raw:
            with contextlib.suppress(ValueError):
                soft_window = max(1, min(72, int(raw)))
    return TelegramConfig(
        bot_token=bot_token,
        chat_id=base.chat_id,
        mode=mode,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        soft_confirm_window_hours=soft_window,
    )
