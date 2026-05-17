"""Tests for the PendingConfirmationStore (ADR-006 §4.5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from selffork_body.sandbox.destructive_whitelist import (
    CandidateAction,
    DestructiveCategory,
    DestructiveWhitelist,
    MatchRule,
)
from selffork_body.sandbox.pending_confirmations import (
    PendingConfirmationStore,
)


def _category(*, window_hours: int = 4, cid: str = "prod_deploy") -> DestructiveCategory:
    return DestructiveCategory(
        id=cid,
        description=f"{cid} category",
        confirm_window_hours=window_hours,
        match_any=(MatchRule(tool="git", args_contains=("push", "origin", "main")),),
    )


def _action() -> CandidateAction:
    return CandidateAction(tool="git", args=("push", "origin", "main"))


def test_request_returns_pending_entry() -> None:
    store = PendingConfirmationStore()
    entry = store.request(
        category=_category(),
        action=_action(),
        workspace_slug="project-x",
    )
    assert entry.status == "pending"
    assert entry.workspace_slug == "project-x"
    assert entry.category_id == "prod_deploy"
    assert entry.command_summary.startswith("git push origin main")


def test_approve_flips_status() -> None:
    store = PendingConfirmationStore()
    entry = store.request(category=_category(), action=_action())
    decided = store.approve(entry.id)
    assert decided is not None
    assert decided.status == "approved"
    assert decided.decided_by == "operator"


def test_cancel_flips_status() -> None:
    store = PendingConfirmationStore()
    entry = store.request(category=_category(), action=_action())
    decided = store.cancel(entry.id)
    assert decided is not None
    assert decided.status == "cancelled"


def test_list_pending_excludes_decided() -> None:
    store = PendingConfirmationStore()
    p1 = store.request(category=_category(), action=_action(), workspace_slug="x")
    p2 = store.request(category=_category(), action=_action(), workspace_slug="x")
    store.approve(p1.id)
    pending = store.list_pending(workspace_slug="x")
    assert {p.id for p in pending} == {p2.id}


def test_expire_stale_marks_old_entries_expired() -> None:
    store = PendingConfirmationStore()
    cat = _category(window_hours=1)
    entry = store.request(category=cat, action=_action())
    # Fast-forward by stubbing the expires_at to the past.
    entry.expires_at = (
        datetime.now(timezone.utc) - timedelta(hours=2)
    ).isoformat()
    flipped = store.expire_stale()
    assert {e.id for e in flipped} == {entry.id}
    stored = store.get(entry.id)
    assert stored is not None
    assert stored.status == "expired"
    assert stored.decided_by == "expired"


def test_approve_after_expire_is_noop() -> None:
    """Once expired, an entry no longer flips on approve."""
    store = PendingConfirmationStore()
    entry = store.request(category=_category(window_hours=1), action=_action())
    entry.expires_at = (
        datetime.now(timezone.utc) - timedelta(hours=2)
    ).isoformat()
    store.expire_stale()
    decided = store.approve(entry.id)
    assert decided is not None
    assert decided.status == "expired"  # didn't flip back to approved


def test_persistence_round_trip(tmp_path: Path) -> None:
    audit = tmp_path / "pending.jsonl"
    store_a = PendingConfirmationStore(audit_path=audit)
    entry = store_a.request(
        category=_category(),
        action=_action(),
        workspace_slug="project-x",
    )
    store_a.approve(entry.id)

    store_b = PendingConfirmationStore(audit_path=audit)
    replay = store_b.get(entry.id)
    assert replay is not None
    assert replay.status == "approved"
    assert replay.workspace_slug == "project-x"


def test_time_left_seconds_drops_to_zero_past_expiry() -> None:
    store = PendingConfirmationStore()
    entry = store.request(category=_category(window_hours=1), action=_action())
    entry.expires_at = (
        datetime.now(timezone.utc) - timedelta(minutes=5)
    ).isoformat()
    assert entry.time_left_seconds() == 0
    assert entry.is_expired() is True
