"""Tests for :class:`ProactiveUsageReader`."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from selffork_orchestrator.usage.proactive import (
    ProactiveUsageReader,
    ProactiveUsageReaderConfig,
)
from selffork_shared.quota import (
    ContextState,
    QuotaSnapshot,
    WindowKind,
    WindowState,
)


def _write_snapshot(state_dir: Path, snap: QuotaSnapshot) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"{snap.cli_id}.json"
    path.write_text(snap.model_dump_json(), encoding="utf-8")
    return path


def _quota(
    cli_id: str,
    *,
    captured_at: datetime | None = None,
) -> QuotaSnapshot:
    return QuotaSnapshot(
        cli_id=cli_id,
        captured_at=captured_at or datetime.now(tz=UTC),
        source="test",
        context=ContextState(used_tokens=10, total_tokens=100, used_pct=10.0),
        windows={
            WindowKind.five_hour: WindowState(
                used_pct=10.0,
                resets_at=datetime.now(tz=UTC) + timedelta(seconds=3600),
                window_seconds=18000,
            ),
        },
    )


def test_read_returns_none_when_file_missing(tmp_path: Path) -> None:
    reader = ProactiveUsageReader(
        ProactiveUsageReaderConfig(state_dir=tmp_path),
    )
    assert reader.read("claude-code") is None


def test_read_returns_none_when_state_dir_missing(tmp_path: Path) -> None:
    reader = ProactiveUsageReader(
        ProactiveUsageReaderConfig(state_dir=tmp_path / "nope"),
    )
    assert reader.read("claude-code") is None
    assert reader.read_all() == {}


def test_read_round_trips_a_fresh_snapshot(tmp_path: Path) -> None:
    snap = _quota("claude-code")
    _write_snapshot(tmp_path, snap)
    reader = ProactiveUsageReader(
        ProactiveUsageReaderConfig(state_dir=tmp_path),
    )
    out = reader.read("claude-code")
    assert out is not None
    assert out.cli_id == "claude-code"
    assert out.context is not None


def test_read_filters_stale_snapshots(tmp_path: Path) -> None:
    stale = _quota("opencode", captured_at=datetime.now(tz=UTC) - timedelta(hours=1))
    _write_snapshot(tmp_path, stale)
    reader = ProactiveUsageReader(
        ProactiveUsageReaderConfig(state_dir=tmp_path, stale_after_seconds=10.0),
    )
    assert reader.read("opencode") is None


def test_read_returns_none_on_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "claude-code.json"
    path.write_text("{not json", encoding="utf-8")
    reader = ProactiveUsageReader(
        ProactiveUsageReaderConfig(state_dir=tmp_path),
    )
    assert reader.read("claude-code") is None


def test_read_returns_none_on_validation_failure(tmp_path: Path) -> None:
    path = tmp_path / "claude-code.json"
    path.write_text(
        '{"cli_id": "claude-code", "captured_at": "not-a-date", "source": "x"}',
        encoding="utf-8",
    )
    reader = ProactiveUsageReader(
        ProactiveUsageReaderConfig(state_dir=tmp_path),
    )
    assert reader.read("claude-code") is None


def test_read_all_skips_dotfiles_and_stale(tmp_path: Path) -> None:
    fresh = _quota("claude-code")
    _write_snapshot(tmp_path, fresh)
    stale = _quota("codex", captured_at=datetime.now(tz=UTC) - timedelta(hours=1))
    _write_snapshot(tmp_path, stale)
    (tmp_path / ".hidden.json").write_text("{}", encoding="utf-8")

    reader = ProactiveUsageReader(
        ProactiveUsageReaderConfig(state_dir=tmp_path, stale_after_seconds=10.0),
    )
    out = reader.read_all()
    assert set(out) == {"claude-code"}
