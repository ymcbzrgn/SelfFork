"""S-Auto Faz G — AutonomySettings + AutonomyStore + apply_preset tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from selffork_orchestrator.heartbeat.autonomy import (
    DEFAULT_AUTONOMY_PATH,
    DEFAULT_CREATIVE_VETO_WINDOW_HOURS,
    AutonomyPreset,
    AutonomySettings,
    AutonomyStore,
    CreativeDial,
    apply_preset,
    default_autonomy_path,
    settings_to_heartbeat_config,
)
from selffork_orchestrator.heartbeat.config import HeartbeatConfig

# ── AutonomyPreset / CreativeDial ────────────────────────────────


def test_preset_count_matches_adr() -> None:
    assert len(list(AutonomyPreset)) == 4


def test_preset_default_is_dengeli() -> None:
    assert AutonomySettings().preset is AutonomyPreset.DENGELI


def test_creative_dial_count() -> None:
    assert len(list(CreativeDial)) == 4


# ── AutonomySettings schema ──────────────────────────────────────


def test_settings_defaults_match_dengeli_preset() -> None:
    settings = AutonomySettings()
    assert settings.enabled is True
    assert settings.supervised_mode is False
    assert settings.creative_dial is CreativeDial.CLOSED
    assert settings.creative_veto_window_hours == DEFAULT_CREATIVE_VETO_WINDOW_HOURS


def test_settings_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        AutonomySettings(unknown_field=True)  # type: ignore[call-arg]


def test_settings_veto_window_clamped() -> None:
    with pytest.raises(ValidationError):
        AutonomySettings(creative_veto_window_hours=0)
    with pytest.raises(ValidationError):
        AutonomySettings(creative_veto_window_hours=200)


# ── apply_preset ─────────────────────────────────────────────────


def test_apply_preset_kapali_disables_daemon() -> None:
    s = apply_preset(AutonomyPreset.KAPALI)
    assert s.enabled is False
    assert s.supervised_mode is False
    assert s.creative_dial is CreativeDial.CLOSED


def test_apply_preset_denetimli_enables_supervised() -> None:
    s = apply_preset(AutonomyPreset.DENETIMLI)
    assert s.enabled is True
    assert s.supervised_mode is True
    assert s.creative_dial is CreativeDial.CLOSED


def test_apply_preset_dengeli_is_default_balanced() -> None:
    s = apply_preset(AutonomyPreset.DENGELI)
    assert s.enabled is True
    assert s.supervised_mode is False
    assert s.creative_dial is CreativeDial.CLOSED


def test_apply_preset_tam_enables_creative_at_spark_only() -> None:
    """Per ADR-008 §11 #4 — pre-M7 creative ceiling stays at spark only."""
    s = apply_preset(AutonomyPreset.TAM)
    assert s.enabled is True
    assert s.creative_dial is CreativeDial.SPARK_ONLY


# ── settings_to_heartbeat_config ─────────────────────────────────


def test_settings_to_config_projects_known_fields() -> None:
    settings = AutonomySettings(
        enabled=True,
        tick_seconds=0.5,
        reconciliation_seconds=300.0,
        max_concurrency=4,
        active_hours="8:00-22:00",
        timezone="Europe/Istanbul",
    )
    config = settings_to_heartbeat_config(settings)
    assert isinstance(config, HeartbeatConfig)
    assert config.tick_seconds == 0.5
    assert config.reconciliation_seconds == 300.0
    assert config.max_concurrency == 4
    assert config.active_hours == "8:00-22:00"
    assert config.timezone == "Europe/Istanbul"


# ── AutonomyStore ────────────────────────────────────────────────


def test_store_read_absent_returns_none(tmp_path: Path) -> None:
    store = AutonomyStore(path=tmp_path / "autonomy.yaml")
    assert store.read() is None


def test_store_read_or_default_falls_back_to_dengeli(tmp_path: Path) -> None:
    store = AutonomyStore(path=tmp_path / "autonomy.yaml")
    settings = store.read_or_default()
    assert settings.preset is AutonomyPreset.DENGELI


def test_store_write_and_read_roundtrip(tmp_path: Path) -> None:
    store = AutonomyStore(path=tmp_path / "autonomy.yaml")
    original = apply_preset(AutonomyPreset.TAM)
    store.write(original)
    loaded = store.read()
    assert loaded is not None
    assert loaded.preset is AutonomyPreset.TAM
    assert loaded.creative_dial is CreativeDial.SPARK_ONLY


def test_store_write_creates_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "autonomy.yaml"
    store = AutonomyStore(path=target)
    store.write(AutonomySettings())
    assert target.is_file()


def test_store_write_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "autonomy.yaml"
    store = AutonomyStore(path=target)
    store.write(AutonomySettings())
    assert not (tmp_path / "autonomy.yaml.tmp").exists()


def test_store_yaml_is_human_readable(tmp_path: Path) -> None:
    target = tmp_path / "autonomy.yaml"
    store = AutonomyStore(path=target)
    store.write(apply_preset(AutonomyPreset.DENETIMLI))
    body = target.read_text(encoding="utf-8")
    data = yaml.safe_load(body)
    assert data["preset"] == "denetimli"
    assert data["supervised_mode"] is True


def test_store_read_invalid_yaml_returns_none(tmp_path: Path) -> None:
    target = tmp_path / "autonomy.yaml"
    target.write_text("this: is: bad: yaml", encoding="utf-8")
    store = AutonomyStore(path=target)
    assert store.read() is None


def test_store_read_unknown_field_returns_none(tmp_path: Path) -> None:
    target = tmp_path / "autonomy.yaml"
    target.write_text("unknown_field: 1\n", encoding="utf-8")
    store = AutonomyStore(path=target)
    assert store.read() is None  # extra="forbid"


def test_default_autonomy_path_under_selffork() -> None:
    path = default_autonomy_path()
    assert "selffork" in str(path)
    assert path.name == "autonomy.yaml"
    assert DEFAULT_AUTONOMY_PATH.endswith("autonomy.yaml")
