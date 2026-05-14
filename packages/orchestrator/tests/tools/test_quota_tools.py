"""Tests for quota observation tools (``quota_snapshot``, ``available_clis``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from selffork_orchestrator.tools.base import ToolCall, ToolContext, ToolRegistry
from selffork_orchestrator.tools.quota import build_quota_tools
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


def _registry() -> ToolRegistry:
    return ToolRegistry(specs=build_quota_tools())


def _ctx(reader: ProactiveUsageReader, **overrides: object) -> ToolContext:
    return ToolContext(
        session_id=str(overrides.get("session_id", "session-1")),
        project_slug=overrides.get("project_slug"),  # type: ignore[arg-type]
        project_store=object(),
        proactive_reader=reader,
        cli_agent_name=overrides.get("cli_agent_name", "claude-code"),  # type: ignore[arg-type]
    )


def _write_snapshot(state_dir: Path, snap: QuotaSnapshot) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / f"{snap.cli_id}.json").write_text(
        snap.model_dump_json(),
        encoding="utf-8",
    )


def _quota(
    cli_id: str,
    *,
    used_pct: float = 50.0,
    captured_at: datetime | None = None,
) -> QuotaSnapshot:
    return QuotaSnapshot(
        cli_id=cli_id,
        captured_at=captured_at or datetime.now(tz=UTC),
        source="test",
        context=ContextState(used_tokens=10, total_tokens=100, used_pct=10.0),
        windows={
            WindowKind.five_hour: WindowState(
                used_pct=used_pct,
                resets_at=datetime.now(tz=UTC) + timedelta(hours=2),
                window_seconds=18000,
            ),
        },
    )


# ── quota_snapshot ────────────────────────────────────────────────────────────


def test_quota_snapshot_returns_specific_cli(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, _quota("claude-code", used_pct=42.0))
    reader = ProactiveUsageReader(ProactiveUsageReaderConfig(state_dir=tmp_path))
    reg = _registry()
    result = reg.invoke(
        ToolCall(tool="quota_snapshot", args={"cli_id": "claude-code"}, order_in_reply=0),
        _ctx(reader),
    )
    assert result.status == "ok"
    payload = result.payload or {}
    assert payload["cli_id"] == "claude-code"
    assert payload["snapshot"]["cli_id"] == "claude-code"


def test_quota_snapshot_returns_all_when_cli_id_omitted(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, _quota("claude-code"))
    _write_snapshot(tmp_path, _quota("codex"))
    reader = ProactiveUsageReader(ProactiveUsageReaderConfig(state_dir=tmp_path))
    reg = _registry()
    result = reg.invoke(
        ToolCall(tool="quota_snapshot", args={}, order_in_reply=0),
        _ctx(reader),
    )
    assert result.status == "ok"
    payload = result.payload or {}
    assert payload["fresh_count"] == 2
    assert set(payload["snapshots"]) == {"claude-code", "codex"}


def test_quota_snapshot_returns_none_for_missing_cli(tmp_path: Path) -> None:
    reader = ProactiveUsageReader(ProactiveUsageReaderConfig(state_dir=tmp_path))
    reg = _registry()
    result = reg.invoke(
        ToolCall(
            tool="quota_snapshot",
            args={"cli_id": "claude-code"},
            order_in_reply=0,
        ),
        _ctx(reader),
    )
    assert result.status == "ok"
    payload = result.payload or {}
    assert payload["snapshot"] is None


# ── available_clis ─────────────────────────────────────────────────────────────


def test_available_clis_lists_registered_with_unknown_for_missing(tmp_path: Path) -> None:
    reader = ProactiveUsageReader(ProactiveUsageReaderConfig(state_dir=tmp_path))
    reg = _registry()
    result = reg.invoke(
        ToolCall(tool="available_clis", args={}, order_in_reply=0),
        _ctx(reader),
    )
    assert result.status == "ok"
    payload = result.payload or {}
    cli_ids = {row["cli_id"] for row in payload["clis"]}
    assert {"claude-code", "codex", "gemini-cli", "opencode"} <= cli_ids
    assert all(row["status"] == "unknown" for row in payload["clis"])
    assert payload["active_cli"] == "claude-code"


def test_available_clis_marks_exhausted_above_threshold(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, _quota("claude-code", used_pct=98.0))
    _write_snapshot(tmp_path, _quota("codex", used_pct=20.0))
    reader = ProactiveUsageReader(ProactiveUsageReaderConfig(state_dir=tmp_path))
    reg = _registry()
    result = reg.invoke(
        ToolCall(tool="available_clis", args={}, order_in_reply=0),
        _ctx(reader),
    )
    payload = result.payload or {}
    rows_by_id = {row["cli_id"]: row for row in payload["clis"]}
    assert rows_by_id["claude-code"]["status"] == "exhausted"
    assert rows_by_id["claude-code"]["exhausted"] is True
    assert rows_by_id["codex"]["status"] == "ok"
    assert rows_by_id["codex"]["exhausted"] is False
