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
)
from selffork_orchestrator.dashboard.settings.store import YamlSettingsStore

__all__ = [
    "DEFAULT_DESTRUCTIVE_OVERRIDE_PATH",
    "CodexBarUserConfig",
    "ModelEndpointConfig",
    "ModelEndpointHealth",
    "YamlSettingsStore",
    "default_codexbar_user_store",
    "default_model_endpoint_store",
    "destructive_whitelist_source",
    "load_effective_destructive_whitelist",
    "resolve_destructive_whitelist_path",
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
