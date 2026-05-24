"""Tests for the affinity-landscape snapshot (cross-process read bridge)."""
from __future__ import annotations

from pathlib import Path

from selffork_orchestrator.router.affinity_snapshot import (
    affinity_snapshot_path,
    read_affinity_snapshot,
    write_affinity_snapshot,
)


def test_write_read_roundtrip(tmp_path: Path) -> None:
    metadata: dict[str, object] = {
        "chosen_cli": "claude-code",
        "chosen_model": "opus",
        "scores": {"claude-code:opus": 0.73, "codex:gpt-5.5": 0.6},
        "match_levels": {"claude-code:opus": "project"},
    }
    write_affinity_snapshot("proj-1", metadata, home=tmp_path)
    data = read_affinity_snapshot("proj-1", home=tmp_path)
    assert data is not None
    assert data["workspace"] == "proj-1"
    assert "recorded_at" in data
    assert data["chosen_cli"] == "claude-code"
    assert data["scores"]["claude-code:opus"] == 0.73


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_affinity_snapshot("never-written", home=tmp_path) is None


def test_read_malformed_returns_none(tmp_path: Path) -> None:
    path = affinity_snapshot_path("broken", home=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert read_affinity_snapshot("broken", home=tmp_path) is None


def test_path_sanitizes_workspace(tmp_path: Path) -> None:
    path = affinity_snapshot_path("a/b c", home=tmp_path)
    assert path.name == "a-b-c.json"
    assert path.parent == tmp_path / "router" / "affinity_snapshot"


def test_write_atomic_overwrite(tmp_path: Path) -> None:
    write_affinity_snapshot("w", {"v": 1}, home=tmp_path)
    write_affinity_snapshot("w", {"v": 2}, home=tmp_path)
    data = read_affinity_snapshot("w", home=tmp_path)
    assert data is not None
    assert data["v"] == 2
