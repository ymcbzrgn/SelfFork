"""Tests for the dashboard pending-confirmation expiry sweeper (S3 Phase B)."""

from __future__ import annotations

import asyncio

import pytest

from selffork_body.sandbox.destructive_whitelist import (
    CandidateAction,
    DestructiveCategory,
    MatchRule,
)
from selffork_body.sandbox.pending_confirmations import PendingConfirmationStore
from selffork_orchestrator.telegram.expire_loop import expire_loop


@pytest.mark.asyncio
async def test_expire_loop_flips_stale_entries() -> None:
    """A 0-hour window expires on first sweep; the loop catches it."""
    store = PendingConfirmationStore(audit_path=None)
    short = DestructiveCategory(
        id="immediate",
        description="immediate expire",
        confirm_window_hours=0,
        match_any=(MatchRule(tool="rm", args_contains=("-rf",)),),
    )
    entry = store.request(
        category=short,
        action=CandidateAction(tool="rm", args=("-rf", "/tmp/x")),
        workspace_slug=None,
    )
    assert entry.status == "pending"

    task = asyncio.create_task(
        expire_loop(store=store, interval_seconds=0.02)
    )
    # Let one sweep land.
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    final = store.get(entry.id)
    assert final is not None
    assert final.status == "expired"


@pytest.mark.asyncio
async def test_expire_loop_rejects_invalid_interval() -> None:
    store = PendingConfirmationStore(audit_path=None)
    with pytest.raises(ValueError):
        await expire_loop(store=store, interval_seconds=0)


@pytest.mark.asyncio
async def test_expire_loop_cancel_runs_final_sweep() -> None:
    """Cancelling the loop still drains any in-flight expiry."""
    store = PendingConfirmationStore(audit_path=None)
    cat = DestructiveCategory(
        id="immediate",
        description="immediate expire",
        confirm_window_hours=0,
        match_any=(MatchRule(tool="rm", args_contains=("-rf",)),),
    )
    # Start the loop before opening the entry so the request lands
    # while the loop is asleep; cancel before the next tick fires.
    task = asyncio.create_task(
        expire_loop(store=store, interval_seconds=10.0)
    )
    # Give the loop a moment to enter its first sleep.
    await asyncio.sleep(0.01)
    entry = store.request(
        category=cat,
        action=CandidateAction(tool="rm", args=("-rf", "/")),
        workspace_slug=None,
    )
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    final = store.get(entry.id)
    assert final is not None
    assert final.status == "expired"  # final sweep on shutdown
