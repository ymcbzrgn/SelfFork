"""S-Auto Faz E — Checkpoint + CheckpointWriter tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from selffork_orchestrator.heartbeat.checkpoint import (
    Checkpoint,
    CheckpointWriter,
    default_checkpoint_path,
)


def _ck(**overrides: object) -> Checkpoint:
    base: dict[str, object] = dict(
        step="act",
        progress="tick=1 workspace=alpha failures=0",
        next_action="task_başlat",
    )
    base.update(overrides)
    return Checkpoint(**base)  # type: ignore[arg-type]


# ── Schema ────────────────────────────────────────────────────────


def test_checkpoint_minimal_fields() -> None:
    cp = _ck()
    assert cp.step == "act"
    assert cp.next_action == "task_başlat"
    assert cp.updated_at.tzinfo is UTC


def test_checkpoint_is_frozen() -> None:
    cp = _ck()
    with pytest.raises(ValidationError):
        cp.step = "edited"  # type: ignore[misc]


def test_checkpoint_serializes_json() -> None:
    cp = _ck(updated_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC))
    body = cp.model_dump_json()
    assert '"step":"act"' in body
    assert '"next_action":"task_başlat"' in body


# ── Writer ────────────────────────────────────────────────────────


def test_writer_creates_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "checkpoint.json"
    writer = CheckpointWriter(path=target)
    writer.write(_ck())
    assert target.is_file()


def test_writer_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "checkpoint.json"
    writer = CheckpointWriter(path=target)
    original = _ck(step="perceive", next_action="bekle")
    writer.write(original)
    loaded = writer.read()
    assert loaded is not None
    assert loaded.step == "perceive"
    assert loaded.next_action == "bekle"


def test_writer_write_is_atomic(tmp_path: Path) -> None:
    """The temp file should disappear after a successful write."""
    target = tmp_path / "checkpoint.json"
    writer = CheckpointWriter(path=target)
    writer.write(_ck())
    assert target.is_file()
    assert not (tmp_path / "checkpoint.json.tmp").exists()


def test_writer_write_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "checkpoint.json"
    writer = CheckpointWriter(path=target)
    writer.write(_ck(step="perceive"))
    writer.write(_ck(step="act"))
    loaded = writer.read()
    assert loaded is not None
    assert loaded.step == "act"


def test_writer_write_unless_manual_preserves_existing(tmp_path: Path) -> None:
    target = tmp_path / "checkpoint.json"
    writer = CheckpointWriter(path=target)
    writer.write(_ck(step="manual"))
    wrote = writer.write_unless_manual(_ck(step="auto"))
    assert wrote is False
    loaded = writer.read()
    assert loaded is not None
    assert loaded.step == "manual"


def test_writer_write_unless_manual_writes_when_absent(tmp_path: Path) -> None:
    writer = CheckpointWriter(path=tmp_path / "checkpoint.json")
    wrote = writer.write_unless_manual(_ck(step="auto"))
    assert wrote is True


def test_writer_read_returns_none_when_absent(tmp_path: Path) -> None:
    writer = CheckpointWriter(path=tmp_path / "absent.json")
    assert writer.read() is None


def test_writer_read_returns_none_when_corrupt(tmp_path: Path) -> None:
    target = tmp_path / "checkpoint.json"
    target.write_text("not json", encoding="utf-8")
    writer = CheckpointWriter(path=target)
    assert writer.read() is None


def test_writer_clear_removes_file(tmp_path: Path) -> None:
    target = tmp_path / "checkpoint.json"
    writer = CheckpointWriter(path=target)
    writer.write(_ck())
    writer.clear()
    assert not target.exists()


def test_writer_clear_idempotent_when_absent(tmp_path: Path) -> None:
    writer = CheckpointWriter(path=tmp_path / "absent.json")
    writer.clear()  # no raise


def test_writer_default_path() -> None:
    assert default_checkpoint_path().name == "checkpoint.json"
    assert default_checkpoint_path().parent.name == "heartbeat"


# ── ADR-010 §2.2.6 — cross-tick resume workspace ──────────────────


def test_checkpoint_workspace_defaults_none() -> None:
    assert _ck().workspace is None


def test_checkpoint_workspace_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "checkpoint.json"
    writer = CheckpointWriter(path=target)
    writer.write(_ck(workspace="beta"))
    loaded = writer.read()
    assert loaded is not None
    assert loaded.workspace == "beta"


def test_checkpoint_reads_legacy_without_workspace(tmp_path: Path) -> None:
    """A pre-S-Vision checkpoint (no ``workspace`` key) still validates."""
    target = tmp_path / "checkpoint.json"
    target.write_text(
        '{"step":"act","progress":"p","next_action":"task_başlat",'
        '"updated_at":"2026-05-23T12:00:00+00:00"}',
        encoding="utf-8",
    )
    loaded = CheckpointWriter(path=target).read()
    assert loaded is not None
    assert loaded.workspace is None
