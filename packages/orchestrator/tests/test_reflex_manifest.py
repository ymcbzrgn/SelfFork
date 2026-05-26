"""Tests for :module:`selffork_orchestrator.reflex_manifest`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from selffork_orchestrator.reflex_manifest import (
    AdapterManifest,
    load_adapter_manifest,
)


def test_load_missing_manifest_returns_honest_empty(tmp_path: Path) -> None:
    result = load_adapter_manifest(tmp_path / "absent.json")
    assert isinstance(result, AdapterManifest)
    assert result.trained is False
    assert result.version is None
    assert result.method is None
    assert result.message is not None
    assert "No adapter manifest" in result.message


def test_load_complete_manifest(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    two_days_ago = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    path.write_text(
        f'{{"version": "v0.5", "method": "QLoRA", '
        f'"trained_at": "{two_days_ago}", "examples": 7777}}',
        encoding="utf-8",
    )
    result = load_adapter_manifest(path)
    assert result.trained is True
    assert result.version == "v0.5"
    assert result.method == "QLoRA"
    assert result.examples == 7777
    assert result.age_days is not None
    assert result.age_days >= 2


def test_load_rejects_bool_examples_audit_god_major_1(tmp_path: Path) -> None:
    """Bool is a subclass of int; manifest with examples=true must NOT coerce to 1."""
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"version": "v0.5", "examples": true}',
        encoding="utf-8",
    )
    result = load_adapter_manifest(path)
    assert result.trained is True
    assert result.examples is None


def test_load_invalid_json_returns_clean_empty(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{not json", encoding="utf-8")
    result = load_adapter_manifest(path)
    assert result.trained is False
    assert "invalid JSON" in (result.message or "")


def test_load_non_object_root_returns_clean_empty(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    result = load_adapter_manifest(path)
    assert result.trained is False
    assert "not a JSON object" in (result.message or "")


def test_load_invalid_trained_at_keeps_string_drops_age(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"version": "v0.5", "trained_at": "not-iso-format"}',
        encoding="utf-8",
    )
    result = load_adapter_manifest(path)
    assert result.trained is True
    assert result.trained_at == "not-iso-format"
    assert result.age_days is None


def test_load_naive_datetime_treated_as_utc(tmp_path: Path) -> None:
    """ISO format without tz info should not crash; we assume UTC."""
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"trained_at": "2026-05-01T00:00:00"}',
        encoding="utf-8",
    )
    result = load_adapter_manifest(path)
    assert result.trained is True
    assert result.age_days is not None
    assert result.age_days >= 0


def test_load_rejects_float_examples(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"examples": 3.14}',
        encoding="utf-8",
    )
    result = load_adapter_manifest(path)
    assert result.trained is True
    assert result.examples is None


def test_load_rejects_string_examples(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"examples": "1234"}',
        encoding="utf-8",
    )
    result = load_adapter_manifest(path)
    assert result.trained is True
    assert result.examples is None
