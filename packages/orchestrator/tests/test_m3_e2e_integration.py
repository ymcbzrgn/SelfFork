"""End-to-end M3 integration smoke tests.

Covers the cross-module wiring of the M3 CLI Surfing milestone:
snapper fleet → SnapperRunner → ProactiveUsageReader → autopilot tools
→ ToolRegistry. A regression in any of these signals breakage in the
auto-pilot's quota awareness chain.

These tests are intentionally end-to-end (no per-component mocking
beyond what's strictly necessary for isolation) — Order 9 deliverable.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from selffork_orchestrator.snappers import (
    build_default_snappers,
    registered_snapper_ids,
    snapshot_path,
)
from selffork_orchestrator.tools import build_default_registry
from selffork_orchestrator.tools.base import ToolCall, ToolContext
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

# ── ToolRegistry composition ──────────────────────────────────────────────────


def test_default_registry_includes_jr_autopilot_fleet() -> None:
    """build_default_registry must compose Mind + Kanban + autopilot in one go."""
    registry = build_default_registry()
    actual = set(registry.names())
    expected = {
        # Order 4 — Jr autopilot read tools:
        "quota_snapshot",
        "available_clis",
        "session_state",
        "mind_recall",
        # Order 4 — Jr autopilot act tools:
        "rotate_to",
        "sleep_until",
        "notify_telegram",
        "compact_context",
        "mark_done",
        # Order 4 — Jr autopilot reflect tools:
        "mind_note_add",
        "cancel_pending",
    }
    missing = expected - actual
    assert missing == set(), f"missing autopilot tools: {missing}"


def test_default_registry_has_at_least_eleven_jr_autopilot_tools() -> None:
    """11-tool surface budget — BiasBusters paper: ≥20 tool patterns leak bias."""
    registry = build_default_registry()
    autopilot_tools = {
        "quota_snapshot",
        "available_clis",
        "session_state",
        "mind_recall",
        "rotate_to",
        "sleep_until",
        "notify_telegram",
        "compact_context",
        "mark_done",
        "mind_note_add",
        "cancel_pending",
    }
    assert autopilot_tools <= set(registry.names())
    assert len(autopilot_tools) == 11


def test_every_autopilot_tool_has_json_schema() -> None:
    """Each tool must expose Pydantic-derived JSON schema for the catalog."""
    registry = build_default_registry()
    autopilot = [
        "quota_snapshot",
        "available_clis",
        "session_state",
        "mark_done",
        "cancel_pending",
        "rotate_to",
        "sleep_until",
        "notify_telegram",
        "compact_context",
    ]
    for name in autopilot:
        spec = registry.get(name)
        assert spec is not None
        schema = spec.json_schema()
        assert isinstance(schema, dict)
        assert "type" in schema or "properties" in schema or "$defs" in schema


# ── Snapper fleet ─────────────────────────────────────────────────────────────


def test_default_snappers_cover_active_fleet() -> None:
    """Default fleet = 4 wired CLI agents (minimax + zai via opencode)."""
    snappers = build_default_snappers()
    cli_ids = {s.cli_id for s in snappers}
    assert cli_ids == {
        "claude-code",
        "codex",
        "gemini-cli",
        "opencode",
    }


def test_registered_snapper_ids_matches_default_fleet() -> None:
    snappers = build_default_snappers()
    assert {s.cli_id for s in snappers} == set(registered_snapper_ids())


def test_snapshot_path_uses_default_cli_state_dir() -> None:
    path = snapshot_path("claude-code")
    assert path.parent.name == "cli-state"
    assert path.parent.parent.name == ".selffork"
    assert path.name == "claude-code.json"


# ── Snapper → ProactiveUsageReader → quota_snapshot tool round trip ───────────


def _write_quota(state_dir: Path, snap: QuotaSnapshot) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / f"{snap.cli_id}.json").write_text(
        snap.model_dump_json(),
        encoding="utf-8",
    )


def test_quota_snapshot_tool_round_trips_through_reader(tmp_path: Path) -> None:
    """Verify the full quota chain: snapshot file → reader → tool."""
    snap = QuotaSnapshot(
        cli_id="codex",
        captured_at=datetime.now(tz=UTC),
        source="rollout-jsonl:test",
        context=ContextState(used_tokens=1500, total_tokens=200_000, used_pct=0.75),
        windows={
            WindowKind.five_hour: WindowState(
                used_pct=23.5,
                resets_at=datetime.now(tz=UTC) + timedelta(hours=4),
                window_seconds=18000,
            ),
            WindowKind.seven_day: WindowState(
                used_pct=41.2,
                resets_at=datetime.now(tz=UTC) + timedelta(days=6),
                window_seconds=604800,
            ),
        },
    )
    _write_quota(tmp_path, snap)

    reader = ProactiveUsageReader(
        ProactiveUsageReaderConfig(state_dir=tmp_path),
    )
    registry = build_default_registry()
    ctx = ToolContext(
        session_id="session-1",
        project_slug=None,
        project_store=object(),
        proactive_reader=reader,
        cli_agent_name="codex",
    )
    result = registry.invoke(
        ToolCall(
            tool="quota_snapshot",
            args={"cli_id": "codex"},
            order_in_reply=0,
        ),
        ctx,
    )
    assert result.status == "ok"
    payload = result.payload or {}
    assert payload["cli_id"] == "codex"
    assert payload["snapshot"]["cli_id"] == "codex"
    five_hour = payload["snapshot"]["windows"]["five_hour"]
    assert five_hour["used_pct"] == 23.5


def test_available_clis_tool_marks_exhausted_above_threshold(tmp_path: Path) -> None:
    """End-to-end: snapper writes 96% snapshot → tool reports 'exhausted'."""
    snap = QuotaSnapshot(
        cli_id="claude-code",
        captured_at=datetime.now(tz=UTC),
        source="statusline.sh",
        context=ContextState(used_tokens=10, total_tokens=1_000_000, used_pct=0.001),
        windows={
            WindowKind.five_hour: WindowState(
                used_pct=96.5,
                resets_at=datetime.now(tz=UTC) + timedelta(hours=1),
                window_seconds=18000,
            ),
        },
    )
    _write_quota(tmp_path, snap)

    reader = ProactiveUsageReader(
        ProactiveUsageReaderConfig(state_dir=tmp_path),
    )
    registry = build_default_registry()
    ctx = ToolContext(
        session_id="s",
        project_slug=None,
        project_store=object(),
        proactive_reader=reader,
        cli_agent_name="claude-code",
    )
    result = registry.invoke(
        ToolCall(tool="available_clis", args={}, order_in_reply=0),
        ctx,
    )
    payload = result.payload or {}
    rows = {row["cli_id"]: row for row in payload["clis"]}
    assert rows["claude-code"]["status"] == "exhausted"
    assert rows["claude-code"]["exhausted"] is True
    # Other CLIs without snapshots → "unknown" (not exhausted).
    # minimax-cli + zai are routed via opencode (operator 2026-05-26)
    # so they no longer appear in the default snapper fleet's clis list.
    assert rows["codex"]["status"] == "unknown"
    assert rows["gemini-cli"]["status"] == "unknown"
    assert rows["opencode"]["status"] == "unknown"
    assert "minimax-cli" not in rows
    assert "zai" not in rows


def test_rotate_to_validates_against_snapper_registry() -> None:
    """``rotate_to`` rejects hallucinated CLI IDs even when Jr LLM invents them."""
    registry = build_default_registry()
    ctx = ToolContext(
        session_id="s",
        project_slug=None,
        project_store=object(),
        cli_agent_name="claude-code",
    )

    bad = registry.invoke(
        ToolCall(
            tool="rotate_to",
            args={"cli_id": "imaginary-cli"},
            order_in_reply=0,
        ),
        ctx,
    )
    assert (bad.payload or {})["rotation_requested"] is False
    assert "unknown" in (bad.payload or {})["error"].lower()

    good = registry.invoke(
        ToolCall(
            tool="rotate_to",
            args={"cli_id": "codex", "reason": "test"},
            order_in_reply=0,
        ),
        ctx,
    )
    payload = good.payload or {}
    assert payload["rotation_requested"] is True
    assert payload["from_cli"] == "claude-code"
    assert payload["to_cli"] == "codex"


def test_session_state_reflects_full_subsystem_wiring() -> None:
    """All wires connected → session_state confirms it."""
    registry = build_default_registry()
    ctx = ToolContext(
        session_id="s",
        project_slug="demo",
        project_store=object(),
        mind_store=object(),
        mind_retriever=object(),
        episodic_writer=object(),
        cli_agent_name="codex",
        proactive_reader=ProactiveUsageReader(),
        launchd_scheduler=object(),
    )
    result = registry.invoke(
        ToolCall(tool="session_state", args={}, order_in_reply=0),
        ctx,
    )
    payload = result.payload or {}
    assert payload["session_id"] == "s"
    assert payload["project_slug"] == "demo"
    assert payload["active_cli"] == "codex"
    assert payload["mind_enabled"] is True
    assert payload["proactive_quota_wired"] is True
    assert payload["launchd_wired"] is True
