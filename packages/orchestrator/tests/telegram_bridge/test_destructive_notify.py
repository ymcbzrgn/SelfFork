"""Tests for the destructive-action Telegram message renderer (S3 Phase B).

Pure unit tests — no PTB, no HTTP. Asserts message shape, HTML escape,
callback_data round-trip, and per-op rendering.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from selffork_body.sandbox.pending_confirmations import PendingConfirmation
from selffork_orchestrator.telegram.destructive_notify import (
    CALLBACK_PREFIX,
    build_callback_data,
    build_message,
    flatten_keyboard,
    parse_callback_data,
)


def _make_entry(
    *,
    cid: str = "abc123",
    workspace: str | None = "demo",
    description: str = "PROD push",
    summary: str = "git push origin main",
    expires_in_minutes: int = 240,
    status: str = "pending",
) -> PendingConfirmation:
    now = datetime.now(tz=UTC)
    return PendingConfirmation(
        id=cid,
        workspace_slug=workspace,
        category_id="prod_deploy",
        category_description=description,
        command_summary=summary,
        action_payload={"tool": "git", "args": ["push", "origin", "main"]},
        asked_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=expires_in_minutes)).isoformat(),
        status=status,  # type: ignore[arg-type]
    )


# ── callback_data ─────────────────────────────────────────────────────────


def test_build_callback_data_formats_namespace() -> None:
    assert build_callback_data("approve", "abc123") == "pending:approve:abc123"


def test_build_callback_data_rejects_unknown_action() -> None:
    with pytest.raises(ValueError):
        build_callback_data("nuke", "abc")  # type: ignore[arg-type]


def test_parse_callback_data_roundtrip() -> None:
    raw = build_callback_data("cancel", "deadbeef")
    parsed = parse_callback_data(raw)
    assert parsed == ("cancel", "deadbeef")


def test_parse_callback_data_returns_none_for_foreign_namespace() -> None:
    assert parse_callback_data("other:approve:abc") is None
    assert parse_callback_data("pending:bogus:abc") is None
    assert parse_callback_data("pending:approve") is None  # missing id
    assert parse_callback_data("") is None


def test_parse_callback_data_rejects_empty_id() -> None:
    assert parse_callback_data("pending:approve:") is None


# ── build_message: request ────────────────────────────────────────────────


def test_request_message_contains_keyboard_and_workspace() -> None:
    entry = _make_entry()
    msg = build_message(entry, "request")
    assert msg.level == "warn"
    assert "Self Jr" in msg.text
    assert "demo" in msg.text
    assert "PROD push" in msg.text
    assert "git push origin main" in msg.text
    assert msg.keyboard is not None
    buttons = list(flatten_keyboard(msg.keyboard))
    assert len(buttons) == 4
    actions = [b.callback_data for b in buttons]
    assert actions[0].startswith(f"{CALLBACK_PREFIX}:approve:")
    assert actions[1].startswith(f"{CALLBACK_PREFIX}:cancel:")
    assert actions[2].startswith(f"{CALLBACK_PREFIX}:extend:")
    assert actions[3].startswith(f"{CALLBACK_PREFIX}:ask:")


def test_request_message_html_escapes_command_summary() -> None:
    entry = _make_entry(summary="rm -rf <important>&'data'")
    msg = build_message(entry, "request")
    assert "&lt;important&gt;" in msg.text
    assert "&amp;" in msg.text


def test_request_message_orphan_workspace_label() -> None:
    entry = _make_entry(workspace=None)
    msg = build_message(entry, "request")
    assert "(orphan run)" in msg.text


# ── build_message: approve / cancel / expire / extend ─────────────────────


def test_approve_message_has_no_keyboard() -> None:
    entry = _make_entry(status="approved")
    msg = build_message(entry, "approve")
    assert msg.keyboard is None
    assert "Approved" in msg.text
    assert msg.level == "info"


def test_cancel_message_has_no_keyboard() -> None:
    entry = _make_entry(status="cancelled")
    msg = build_message(entry, "cancel")
    assert msg.keyboard is None
    assert "Cancelled" in msg.text


def test_expire_message_is_critical() -> None:
    entry = _make_entry(status="expired")
    msg = build_message(entry, "expire")
    assert msg.level == "crit"
    assert "expired" in msg.text.lower()
    assert msg.keyboard is None


def test_extend_message_keeps_keyboard() -> None:
    entry = _make_entry(expires_in_minutes=480)  # extended out
    msg = build_message(entry, "extend")
    assert msg.keyboard is not None
    assert "extended" in msg.text.lower()
