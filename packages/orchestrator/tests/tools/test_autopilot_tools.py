"""Tests for Jr autopilot act tools."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from selffork_orchestrator.resume.cron import LaunchdScheduler
from selffork_orchestrator.tools.autopilot import build_autopilot_tools
from selffork_orchestrator.tools.base import ToolCall, ToolContext, ToolRegistry


def _registry() -> ToolRegistry:
    return ToolRegistry(specs=build_autopilot_tools())


def _ctx(**overrides: object) -> ToolContext:
    return ToolContext(
        session_id=str(overrides.get("session_id", "session-1")),
        project_slug=overrides.get("project_slug"),  # type: ignore[arg-type]
        project_store=object(),
        cli_agent_name=overrides.get("cli_agent_name", "claude-code"),  # type: ignore[arg-type]
        launchd_scheduler=overrides.get("launchd_scheduler"),  # type: ignore[arg-type]
        resume_store=overrides.get("resume_store"),  # type: ignore[arg-type]
    )


# ── rotate_to ─────────────────────────────────────────────────────────────────


def test_rotate_to_unknown_cli_returns_error() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(tool="rotate_to", args={"cli_id": "nonexistent"}, order_in_reply=0),
        _ctx(),
    )
    payload = result.payload or {}
    assert payload["rotation_requested"] is False
    assert "unknown cli_id" in payload["error"]


def test_rotate_to_rejects_snapper_only_provider_zai() -> None:
    """``zai`` is a registered SNAPPER (opencode-routed Z.AI provider) but
    NOT a standalone CLIAgent — rotating to it would crash the round-loop
    driver when it tries to instantiate the agent. The validation must
    refuse it explicitly even though the snapper exists.
    """
    reg = _registry()
    result = reg.invoke(
        ToolCall(tool="rotate_to", args={"cli_id": "zai"}, order_in_reply=0),
        _ctx(cli_agent_name="claude-code"),
    )
    payload = result.payload or {}
    assert payload["rotation_requested"] is False
    assert "unknown cli_id" in payload["error"]


def test_rotate_to_same_cli_is_noop() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(
            tool="rotate_to",
            args={"cli_id": "claude-code", "reason": "test"},
            order_in_reply=0,
        ),
        _ctx(cli_agent_name="claude-code"),
    )
    payload = result.payload or {}
    assert payload["rotation_requested"] is False
    assert "no-op" in payload["error"]


def test_rotate_to_valid_swap() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(
            tool="rotate_to",
            args={"cli_id": "codex", "reason": "claude exhausted"},
            order_in_reply=0,
        ),
        _ctx(cli_agent_name="claude-code"),
    )
    payload = result.payload or {}
    assert payload["rotation_requested"] is True
    assert payload["from_cli"] == "claude-code"
    assert payload["to_cli"] == "codex"
    assert payload["reason"] == "claude exhausted"


# ── sleep_until ───────────────────────────────────────────────────────────────


def test_sleep_until_past_epoch_rejects() -> None:
    reg = _registry()
    past = int((datetime.now(tz=UTC) - timedelta(hours=1)).timestamp())
    result = reg.invoke(
        ToolCall(
            tool="sleep_until",
            args={"epoch_seconds": past, "reason": "test"},
            order_in_reply=0,
        ),
        _ctx(),
    )
    payload = result.payload or {}
    assert payload["scheduled"] is False
    assert "past" in payload["error"]


def test_sleep_until_no_scheduler_records_intent() -> None:
    reg = _registry()
    future = int((datetime.now(tz=UTC) + timedelta(hours=2)).timestamp())
    result = reg.invoke(
        ToolCall(
            tool="sleep_until",
            args={
                "epoch_seconds": future,
                "kind": "five_hour",
                "reason": "claude 5h exhausted",
            },
            order_in_reply=0,
        ),
        _ctx(),
    )
    payload = result.payload or {}
    assert payload["scheduled"] is False
    assert "launchd scheduler not wired" in payload["reason_no_scheduler"]
    assert payload["kind"] == "five_hour"


def test_sleep_until_with_scheduler_installs_plist(tmp_path: Path) -> None:
    from selffork_orchestrator.resume.store import (
        ScheduledResume,
        ScheduledResumeStore,
    )

    sched = LaunchdScheduler(
        launch_agents_dir=tmp_path / "LaunchAgents",
        selffork_executable="/usr/local/bin/selffork",
    )
    store = ScheduledResumeStore(root=tmp_path / "scheduled")
    # Pre-write the paused session record so sleep_until can fetch its
    # PRD/workspace paths and produce a plist that won't crash on fire.
    store.save(
        ScheduledResume(
            session_id="abc",
            scheduled_at=datetime.now(tz=UTC),
            resume_at=datetime.now(tz=UTC) + timedelta(hours=1),
            cli_agent="claude-code",
            config_path=None,
            prd_path="/tmp/work/prd.md",
            workspace_path="/tmp/work",
            reason="initial pause",
            kind="five_hour",
        ),
    )
    reg = _registry()
    future = int((datetime.now(tz=UTC) + timedelta(hours=3)).timestamp())
    with patch(
        "selffork_orchestrator.resume.cron.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stderr="", stdout=""),
    ):
        result = reg.invoke(
            ToolCall(
                tool="sleep_until",
                args={"epoch_seconds": future, "kind": "five_hour"},
                order_in_reply=0,
            ),
            _ctx(launchd_scheduler=sched, resume_store=store, session_id="abc"),
        )
    payload = result.payload or {}
    assert payload["scheduled"] is True
    assert payload["kind"] == "five_hour"
    assert "abc" in payload["plist_path"]


def test_sleep_until_rejects_when_no_paused_record(tmp_path: Path) -> None:
    """Without a pre-existing ScheduledResume record, sleep_until cannot
    safely produce a plist (would crash on fire with empty prd_path).
    """
    from selffork_orchestrator.resume.store import ScheduledResumeStore

    sched = LaunchdScheduler(
        launch_agents_dir=tmp_path / "LaunchAgents",
        selffork_executable="/usr/local/bin/selffork",
    )
    empty_store = ScheduledResumeStore(root=tmp_path / "scheduled")
    reg = _registry()
    future = int((datetime.now(tz=UTC) + timedelta(hours=3)).timestamp())
    result = reg.invoke(
        ToolCall(
            tool="sleep_until",
            args={"epoch_seconds": future, "kind": "five_hour"},
            order_in_reply=0,
        ),
        _ctx(
            launchd_scheduler=sched,
            resume_store=empty_store,
            session_id="orphan-session",
        ),
    )
    payload = result.payload or {}
    assert payload["scheduled"] is False
    assert "no paused ScheduledResume record" in payload["error"]


# ── notify_telegram ───────────────────────────────────────────────────────────


def test_notify_telegram_returns_placeholder_until_order_5() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(
            tool="notify_telegram",
            args={"level": "warn", "message": "claude doluyor"},
            order_in_reply=0,
        ),
        _ctx(),
    )
    payload = result.payload or {}
    assert payload["delivered"] is False
    assert payload["level"] == "warn"
    assert "claude doluyor" in payload["message_preview"]


# ── compact_context ───────────────────────────────────────────────────────────


def test_compact_context_default_strategy() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(tool="compact_context", args={}, order_in_reply=0),
        _ctx(),
    )
    payload = result.payload or {}
    assert payload["compaction_requested"] is True
    assert payload["strategy"] == "summary"


def test_compact_context_handoff_strategy() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(
            tool="compact_context",
            args={"strategy": "handoff", "reason": "rotating to codex"},
            order_in_reply=0,
        ),
        _ctx(),
    )
    payload = result.payload or {}
    assert payload["strategy"] == "handoff"
    assert payload["reason"] == "rotating to codex"


def test_compact_context_truncate_strategy() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(
            tool="compact_context",
            args={"strategy": "truncate"},
            order_in_reply=0,
        ),
        _ctx(),
    )
    payload = result.payload or {}
    assert payload["strategy"] == "truncate"
