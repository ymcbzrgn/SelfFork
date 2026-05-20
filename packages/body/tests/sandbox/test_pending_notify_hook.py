"""Tests for ``PendingConfirmationStore.notify_hook`` (S3 Phase B).

The hook bridges the store to the Telegram outbound layer in the
orchestrator. Body itself stays pillar-pure — no PTB imports here.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

import pytest

from selffork_body.sandbox.destructive_whitelist import (
    CandidateAction,
    DestructiveCategory,
    MatchRule,
)
from selffork_body.sandbox.pending_confirmations import (
    NotifyOp,
    PendingConfirmation,
    PendingConfirmationStore,
)


@pytest.fixture
def category() -> DestructiveCategory:
    return DestructiveCategory(
        id="prod_deploy",
        description="PROD push",
        confirm_window_hours=4,
        match_any=(MatchRule(tool="git", args_contains=("push", "origin", "main")),),
    )


@pytest.fixture
def action() -> CandidateAction:
    return CandidateAction(tool="git", args=("push", "origin", "main"))


def _make_store_with_recorder() -> tuple[
    PendingConfirmationStore, list[tuple[NotifyOp, str]]
]:
    """Build a store wired to a recording hook."""
    events: list[tuple[NotifyOp, str]] = []

    def recorder(entry: PendingConfirmation, op: NotifyOp) -> None:
        events.append((op, entry.id))

    store = PendingConfirmationStore(audit_path=None, notify_hook=recorder)
    return store, events


def test_request_invokes_hook(
    category: DestructiveCategory, action: CandidateAction
) -> None:
    store, events = _make_store_with_recorder()
    entry = store.request(
        category=category, action=action, workspace_slug="demo"
    )
    assert events == [("request", entry.id)]


def test_approve_invokes_hook(
    category: DestructiveCategory, action: CandidateAction
) -> None:
    store, events = _make_store_with_recorder()
    entry = store.request(category=category, action=action, workspace_slug=None)
    events.clear()
    store.approve(entry.id, by="test-operator")
    assert events == [("approve", entry.id)]


def test_cancel_invokes_hook(
    category: DestructiveCategory, action: CandidateAction
) -> None:
    store, events = _make_store_with_recorder()
    entry = store.request(category=category, action=action, workspace_slug=None)
    events.clear()
    store.cancel(entry.id, by="test-operator")
    assert events == [("cancel", entry.id)]


def test_extend_invokes_hook(
    category: DestructiveCategory, action: CandidateAction
) -> None:
    store, events = _make_store_with_recorder()
    entry = store.request(category=category, action=action, workspace_slug=None)
    events.clear()
    store.extend(entry.id, hours=2, by="test-operator")
    assert events == [("extend", entry.id)]


def test_extend_advances_expires_at(
    category: DestructiveCategory, action: CandidateAction
) -> None:
    store, _events = _make_store_with_recorder()
    entry = store.request(category=category, action=action, workspace_slug=None)
    before = datetime.datetime.fromisoformat(entry.expires_at)
    updated = store.extend(entry.id, hours=3, by="op")
    assert updated is not None
    after = datetime.datetime.fromisoformat(updated.expires_at)
    delta = (after - before).total_seconds()
    assert abs(delta - 3 * 3600) < 1.0
    assert updated.status == "pending"


def test_extend_rejects_nonpositive(
    category: DestructiveCategory, action: CandidateAction
) -> None:
    store, events = _make_store_with_recorder()
    entry = store.request(category=category, action=action, workspace_slug=None)
    events.clear()
    result = store.extend(entry.id, hours=0)
    # Returns the entry unchanged, no hook invocation.
    assert result is not None
    assert result.expires_at == entry.expires_at
    assert events == []


def test_expire_invokes_hook(
    tmp_path: Path,
    category: DestructiveCategory,
    action: CandidateAction,
) -> None:
    """An expired entry triggers exactly one ``expire`` hook call."""
    short = DestructiveCategory(
        id=category.id,
        description=category.description,
        confirm_window_hours=0,  # immediate expiry on first sweep
        match_any=category.match_any,
    )
    store, events = _make_store_with_recorder()
    entry = store.request(category=short, action=action, workspace_slug=None)
    events.clear()
    flipped = store.expire_stale()
    assert [e.id for e in flipped] == [entry.id]
    assert events == [("expire", entry.id)]


def test_hook_exception_does_not_break_store(
    category: DestructiveCategory,
    action: CandidateAction,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A raising hook must not propagate or corrupt the store state."""

    def bad_hook(entry: PendingConfirmation, op: NotifyOp) -> None:
        raise RuntimeError("telegram down")

    store = PendingConfirmationStore(audit_path=None, notify_hook=bad_hook)
    with caplog.at_level(logging.ERROR):
        entry = store.request(category=category, action=action, workspace_slug=None)
        store.approve(entry.id, by="t")
    # Despite the hook raising, the store mutated correctly.
    final = store.get(entry.id)
    assert final is not None and final.status == "approved"


def test_set_notify_hook_late_binding(
    category: DestructiveCategory, action: CandidateAction
) -> None:
    """``set_notify_hook`` rewires the hook after construction."""
    events: list[NotifyOp] = []

    def recorder(entry: PendingConfirmation, op: NotifyOp) -> None:
        events.append(op)

    store = PendingConfirmationStore(audit_path=None)
    store.request(category=category, action=action, workspace_slug=None)
    assert events == []
    store.set_notify_hook(recorder)
    entry = store.request(category=category, action=action, workspace_slug=None)
    assert events == ["request"]
    store.cancel(entry.id, by="t")
    assert events == ["request", "cancel"]
