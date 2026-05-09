"""Tests for session lifecycle tools (``session_state``, ``mark_done``, ``cancel_pending``)."""
from __future__ import annotations

from unittest.mock import MagicMock

from selffork_orchestrator.tools.base import ToolCall, ToolContext, ToolRegistry
from selffork_orchestrator.tools.session import DONE_SENTINEL, build_session_tools


def _registry() -> ToolRegistry:
    return ToolRegistry(specs=build_session_tools())


def _ctx(**overrides: object) -> ToolContext:
    return ToolContext(
        session_id=str(overrides.get("session_id", "session-1")),
        project_slug=overrides.get("project_slug", "demo"),  # type: ignore[arg-type]
        project_store=object(),
        cli_agent_name=overrides.get("cli_agent_name", "claude-code"),  # type: ignore[arg-type]
        mind_store=overrides.get("mind_store"),  # type: ignore[arg-type]
        mind_retriever=overrides.get("mind_retriever"),  # type: ignore[arg-type]
        episodic_writer=overrides.get("episodic_writer"),  # type: ignore[arg-type]
        proactive_reader=overrides.get("proactive_reader"),  # type: ignore[arg-type]
        launchd_scheduler=overrides.get("launchd_scheduler"),  # type: ignore[arg-type]
    )


# ── session_state ─────────────────────────────────────────────────────────────


def test_session_state_returns_basic_fields() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(tool="session_state", args={}, order_in_reply=0),
        _ctx(),
    )
    assert result.status == "ok"
    payload = result.payload or {}
    assert payload["session_id"] == "session-1"
    assert payload["project_slug"] == "demo"
    assert payload["active_cli"] == "claude-code"
    assert payload["mind_enabled"] is False
    assert payload["proactive_quota_wired"] is False
    assert payload["launchd_wired"] is False


def test_session_state_reflects_mind_enabled() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(tool="session_state", args={}, order_in_reply=0),
        _ctx(
            mind_store=object(),
            mind_retriever=object(),
            episodic_writer=object(),
        ),
    )
    payload = result.payload or {}
    assert payload["mind_enabled"] is True


def test_session_state_reflects_subsystem_wiring() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(tool="session_state", args={}, order_in_reply=0),
        _ctx(
            proactive_reader=object(),
            launchd_scheduler=object(),
        ),
    )
    payload = result.payload or {}
    assert payload["proactive_quota_wired"] is True
    assert payload["launchd_wired"] is True


# ── mark_done ─────────────────────────────────────────────────────────────────


def test_mark_done_returns_sentinel_and_reason() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(
            tool="mark_done",
            args={"reason": "all PRD criteria met"},
            order_in_reply=0,
        ),
        _ctx(),
    )
    assert result.status == "ok"
    payload = result.payload or {}
    assert payload["sentinel"] == DONE_SENTINEL
    assert payload["reason"] == "all PRD criteria met"
    assert payload["session_id"] == "session-1"


def test_mark_done_default_reason_empty() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(tool="mark_done", args={}, order_in_reply=0),
        _ctx(),
    )
    payload = result.payload or {}
    assert payload["sentinel"] == DONE_SENTINEL
    assert payload["reason"] == ""


# ── cancel_pending ────────────────────────────────────────────────────────────


def test_cancel_pending_without_scheduler_returns_false_for_plist() -> None:
    reg = _registry()
    result = reg.invoke(
        ToolCall(
            tool="cancel_pending",
            args={"action_id": "abc", "reason": "user reverted"},
            order_in_reply=0,
        ),
        _ctx(),
    )
    assert result.status == "ok"
    payload = result.payload or {}
    assert payload["action_id"] == "abc"
    assert payload["cancelled_plist"] is False


def test_cancel_pending_calls_uninstall_when_scheduler_wired() -> None:
    fake_scheduler = MagicMock()
    fake_scheduler.uninstall.return_value = True
    reg = _registry()
    result = reg.invoke(
        ToolCall(
            tool="cancel_pending",
            args={"action_id": "session-xyz"},
            order_in_reply=0,
        ),
        _ctx(launchd_scheduler=fake_scheduler),
    )
    assert result.status == "ok"
    payload = result.payload or {}
    assert payload["cancelled_plist"] is True
    fake_scheduler.uninstall.assert_called_once_with("session-xyz")


def test_cancel_pending_swallows_uninstall_exception() -> None:
    fake_scheduler = MagicMock()
    fake_scheduler.uninstall.side_effect = RuntimeError("boom")
    reg = _registry()
    result = reg.invoke(
        ToolCall(
            tool="cancel_pending",
            args={"action_id": "abc"},
            order_in_reply=0,
        ),
        _ctx(launchd_scheduler=fake_scheduler),
    )
    assert result.status == "ok"
    payload = result.payload or {}
    assert payload["cancelled_plist"] is False
