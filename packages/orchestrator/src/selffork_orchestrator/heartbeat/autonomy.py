"""Autonomy Settings — 4 preset + power-user knobs (S-Auto Faz G).

ADR-008 §5.5 + §7 Lock #12: the operator can ratchet Heartbeat
behaviour from completely off to full autonomy through a Settings UI;
**no autonomy tier is hardcoded** outside this module. The four named
presets cover the spectrum:

* ``KAPALI`` — Heartbeat daemon disabled (`SELFFORK_HEARTBEAT_ENABLED=false`
  equivalent). Pure manual operation via ``selffork run``.
* ``DENETIMLI`` — every task-start requires Telegram approval
  (sessizlik = iptal). Maximum human-in-the-loop.
* ``DENGELI`` (default) — executive autonomy on; destructive actions
  still gated through ADR-006 §4.5 soft-confirm; creative mode off.
* ``TAM`` — executive + creative both on; creative dial set by the
  power-user knob.

Persistence: YAML at ``~/.selffork/heartbeat/autonomy.yaml``. The
daemon reads this on boot; the dashboard's ``GET /api/heartbeat/
autonomy`` returns the parsed shape; ``PUT`` writes it back. Effects
become live on next daemon restart — Faz G persists; hot-reload is a
later sprint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field

from selffork_orchestrator.heartbeat.config import (
    DEFAULT_ACTIVE_HOURS,
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_RECONCILIATION_SECONDS,
    DEFAULT_TICK_SECONDS,
    DEFAULT_TIMEZONE,
    HeartbeatConfig,
)

__all__ = [
    "DEFAULT_AUTONOMY_PATH",
    "DEFAULT_CREATIVE_VETO_WINDOW_HOURS",
    "DEFAULT_MORNING_REPORT_TIME",
    "AutonomyPreset",
    "AutonomySettings",
    "AutonomyStore",
    "CreativeDial",
    "apply_preset",
    "default_autonomy_path",
    "settings_to_heartbeat_config",
]


_log = logging.getLogger(__name__)


DEFAULT_AUTONOMY_PATH: Final[str] = "~/.selffork/heartbeat/autonomy.yaml"
DEFAULT_CREATIVE_VETO_WINDOW_HOURS: Final[int] = 4
"""ADR-008 §11 #3 — operator's chosen veto window for big ideas."""

DEFAULT_MORNING_REPORT_TIME: Final[str] = "08:00"


class AutonomyPreset(StrEnum):
    """Four named tiers covering the full operator-trust spectrum.

    Mirrors ADR-008 §5.5 verbatim. Values are the Turkish names the
    operator sees in the Settings dropdown; ASCII names follow PEP 8.
    """

    KAPALI = "kapalı"
    DENETIMLI = "denetimli"
    DENGELI = "dengeli"
    TAM = "tam"


class CreativeDial(StrEnum):
    """Power-user knob for ADR-008 §5.3 Yaratma mode behaviour.

    Pre-M7 default is ``SPARK_ONLY`` (operator decision §11 #4) —
    record ideas but do not auto-code; M7 + operator may raise to
    ``GRADIENT`` (B*C mix) or ``FULL``.
    """

    CLOSED = "closed"
    SPARK_ONLY = "spark_only"
    GRADIENT = "gradient"
    FULL = "full"


class AutonomySettings(BaseModel):
    """Persisted Heartbeat tunables, sourced from the Settings UI."""

    model_config = ConfigDict(extra="forbid")

    preset: AutonomyPreset = AutonomyPreset.DENGELI
    enabled: bool = True
    supervised_mode: bool = False
    creative_dial: CreativeDial = CreativeDial.CLOSED
    creative_veto_window_hours: int = Field(
        default=DEFAULT_CREATIVE_VETO_WINDOW_HOURS, ge=1, le=72
    )
    tick_seconds: float = Field(default=DEFAULT_TICK_SECONDS, ge=0.05)
    reconciliation_seconds: float = Field(
        default=DEFAULT_RECONCILIATION_SECONDS, ge=10.0
    )
    max_concurrency: int = Field(default=DEFAULT_MAX_CONCURRENCY, ge=1)
    active_hours: str = DEFAULT_ACTIVE_HOURS
    timezone: str = DEFAULT_TIMEZONE
    morning_report_enabled: bool = True
    morning_report_time: str = DEFAULT_MORNING_REPORT_TIME


def default_autonomy_path() -> Path:
    return Path(DEFAULT_AUTONOMY_PATH).expanduser()


def apply_preset(preset: AutonomyPreset) -> AutonomySettings:
    """Return a fresh :class:`AutonomySettings` matching ``preset``.

    Power-user knobs (timer interval, active hours, timezone) keep
    their global defaults; the preset only flips the high-level
    behaviour switches. Operators who want unusual cadences edit
    those knobs after applying the preset.
    """
    if preset is AutonomyPreset.KAPALI:
        return AutonomySettings(
            preset=preset,
            enabled=False,
            supervised_mode=False,
            creative_dial=CreativeDial.CLOSED,
        )
    if preset is AutonomyPreset.DENETIMLI:
        return AutonomySettings(
            preset=preset,
            enabled=True,
            supervised_mode=True,
            creative_dial=CreativeDial.CLOSED,
        )
    if preset is AutonomyPreset.DENGELI:
        return AutonomySettings(
            preset=preset,
            enabled=True,
            supervised_mode=False,
            creative_dial=CreativeDial.CLOSED,
        )
    # TAM — executive + creative on; pre-M7 stays at SPARK_ONLY
    # (operator's §11 #4 default ceiling); operator raises further
    # post-M7 through the power-user knob.
    return AutonomySettings(
        preset=AutonomyPreset.TAM,
        enabled=True,
        supervised_mode=False,
        creative_dial=CreativeDial.SPARK_ONLY,
    )


def settings_to_heartbeat_config(
    settings: AutonomySettings,
) -> HeartbeatConfig:
    """Project the persisted Settings into the daemon's runtime config.

    Only the fields :class:`HeartbeatConfig` knows about land here —
    creative dial, supervised mode, morning report, etc. are surfaced
    to other layers (executor, filter) directly from
    :class:`AutonomySettings`.
    """
    return HeartbeatConfig(
        enabled=settings.enabled,
        tick_seconds=settings.tick_seconds,
        reconciliation_seconds=settings.reconciliation_seconds,
        max_concurrency=settings.max_concurrency,
        active_hours=settings.active_hours,
        timezone=settings.timezone,
    )


@dataclass(frozen=True, slots=True)
class AutonomyStore:
    """YAML-backed persistence for :class:`AutonomySettings`.

    The dashboard's ``GET /api/heartbeat/autonomy`` returns the
    persisted shape (default preset when absent); ``PUT`` round-trips
    it. The file is intentionally human-readable so an operator can
    edit it with ``vi`` in a pinch.
    """

    path: Path

    def read(self) -> AutonomySettings | None:
        """Return the persisted settings or ``None`` when absent / bad."""
        if not self.path.is_file():
            return None
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            if not isinstance(data, dict):
                return None
            return AutonomySettings.model_validate(data)
        except (OSError, yaml.YAMLError, ValueError) as exc:
            _log.warning(
                "heartbeat_autonomy_read_failed",
                extra={"path": str(self.path), "error": str(exc)},
            )
            return None

    def read_or_default(
        self, default: AutonomySettings | None = None
    ) -> AutonomySettings:
        """Return persisted settings or a fallback (default preset)."""
        persisted = self.read()
        if persisted is not None:
            return persisted
        return default if default is not None else apply_preset(
            AutonomyPreset.DENGELI
        )

    def write(self, settings: AutonomySettings) -> None:
        """Atomically persist ``settings`` to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body: dict[str, Any] = settings.model_dump(mode="json")
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(
            yaml.safe_dump(body, sort_keys=True, allow_unicode=True),
            encoding="utf-8",
        )
        temp.replace(self.path)

    @classmethod
    def default(cls) -> AutonomyStore:
        return cls(path=default_autonomy_path())
