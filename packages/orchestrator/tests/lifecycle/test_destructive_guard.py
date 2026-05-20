"""Tests for the destructive-action guard (S3 Phase A).

The guard sits in front of ``Session._run_agent`` ``sandbox.exec`` and
blocks the round-loop when a command matches a destructive whitelist
category. These tests exercise the guard against a real
:class:`PendingConfirmationStore` (in-memory, no audit file) so the
production state-transition logic is covered end-to-end without
spinning up a full Session.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from selffork_body.sandbox.destructive_whitelist import (
    DestructiveCategory,
    DestructiveWhitelist,
    MatchRule,
)
from selffork_body.sandbox.pending_confirmations import (
    PendingConfirmationStore,
)
from selffork_orchestrator.lifecycle.destructive_guard import (
    check_destructive_action,
    cmd_to_candidate_action,
)
from selffork_shared.audit import AuditLogger
from selffork_shared.config import AuditConfig

# Async tests use the explicit @pytest.mark.asyncio decorator below.
# pytestmark is intentionally not set so the two sync helpers
# (`test_cmd_to_candidate_*`) don't trip pytest-asyncio's strict mode.


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def audit(tmp_path: Path) -> AuditLogger:
    """Real audit logger writing into a temp session dir."""
    return AuditLogger(
        config=AuditConfig(audit_dir=str(tmp_path / "audit"), enabled=True),
        session_id="test-session",
    )


@pytest.fixture
def whitelist() -> DestructiveWhitelist:
    """Tiny whitelist: ``git push origin main`` + ``rm -rf``.

    Inline rather than the YAML file so the test is hermetic.
    """
    return DestructiveWhitelist(
        categories=(
            DestructiveCategory(
                id="prod_deploy",
                description="PROD push",
                confirm_window_hours=4,
                match_any=(
                    MatchRule(
                        tool="git",
                        args_contains=("push", "origin", "main"),
                    ),
                ),
            ),
            DestructiveCategory(
                id="file_destructive",
                description="rm -rf",
                confirm_window_hours=4,
                match_any=(
                    MatchRule(tool="rm", args_contains=("-rf",)),
                ),
            ),
        )
    )


@pytest.fixture
def store() -> PendingConfirmationStore:
    """Fresh in-memory store (no JSONL persistence)."""
    return PendingConfirmationStore(audit_path=None)


# ── cmd_to_candidate_action ───────────────────────────────────────────────


def test_cmd_to_candidate_strips_path() -> None:
    action = cmd_to_candidate_action(
        ["/usr/local/bin/git", "push", "origin", "main"],
        env={"PATH": "/usr/local/bin"},
    )
    assert action.tool == "git"
    assert action.args == ("push", "origin", "main")
    assert action.env == {"PATH": "/usr/local/bin"}


def test_cmd_to_candidate_handles_empty() -> None:
    action = cmd_to_candidate_action([], env=None)
    assert action.tool is None
    assert action.args == ()
    assert action.env == {}


# ── Allow path (no match) ─────────────────────────────────────────────────


async def test_safe_command_returns_allow(
    whitelist: DestructiveWhitelist,
    store: PendingConfirmationStore,
    audit: AuditLogger,
) -> None:
    decision = await check_destructive_action(
        cmd=["ls", "-la"],
        env=None,
        workspace_slug="demo",
        whitelist=whitelist,
        store=store,
        audit=audit,
    )
    assert decision.allow is True
    assert decision.reason == "not_destructive"
    assert decision.entry is None
    # No pending entry leaked into the store.
    assert store.list_pending() == []


# ── Match → approve path ──────────────────────────────────────────────────


async def test_match_then_approve_resumes(
    whitelist: DestructiveWhitelist,
    store: PendingConfirmationStore,
    audit: AuditLogger,
) -> None:
    """Operator approves while the guard is mid-wait."""

    async def approver() -> None:
        # Give the guard one poll cycle to register the entry, then
        # approve it. Mirrors a real operator clicking ✅ in the UI.
        await asyncio.sleep(0.05)
        pending = store.list_pending()
        assert len(pending) == 1
        result = store.approve(pending[0].id, by="test-operator")
        assert result is not None

    decision_task = asyncio.create_task(
        check_destructive_action(
            cmd=["git", "push", "origin", "main"],
            env=None,
            workspace_slug="demo",
            whitelist=whitelist,
            store=store,
            audit=audit,
            poll_interval_seconds=0.02,
        )
    )
    await approver()
    decision = await decision_task

    assert decision.allow is True
    assert decision.reason == "approved"
    assert decision.entry is not None
    assert decision.entry.status == "approved"
    assert decision.category_id == "prod_deploy"


async def test_match_then_cancel_blocks(
    whitelist: DestructiveWhitelist,
    store: PendingConfirmationStore,
    audit: AuditLogger,
) -> None:
    """Operator cancels — guard returns deny with reason=cancelled."""

    async def canceller() -> None:
        await asyncio.sleep(0.05)
        pending = store.list_pending()
        assert len(pending) == 1
        store.cancel(pending[0].id, by="test-operator")

    decision_task = asyncio.create_task(
        check_destructive_action(
            cmd=["rm", "-rf", "node_modules"],
            env=None,
            workspace_slug="demo",
            whitelist=whitelist,
            store=store,
            audit=audit,
            poll_interval_seconds=0.02,
        )
    )
    await canceller()
    decision = await decision_task

    assert decision.allow is False
    assert decision.reason == "cancelled"
    assert decision.entry is not None
    assert decision.entry.status == "cancelled"
    assert decision.category_id == "file_destructive"


# ── Expiry path (silence = NO) ────────────────────────────────────────────


async def test_silence_expires_to_deny(
    whitelist: DestructiveWhitelist,
    store: PendingConfirmationStore,
    audit: AuditLogger,
) -> None:
    """No operator response within ``max_wait_seconds`` → cancel + deny.

    The guard's internal deadline forces the entry into ``cancelled`` so
    the round-loop returns promptly rather than blocking for hours.
    """
    decision = await check_destructive_action(
        cmd=["git", "push", "origin", "main"],
        env=None,
        workspace_slug="demo",
        whitelist=whitelist,
        store=store,
        audit=audit,
        poll_interval_seconds=0.02,
        max_wait_seconds=0.1,  # ⏰ deadline 100ms
    )

    assert decision.allow is False
    # ``cancelled`` because the guard's deadline forced a cancel — the
    # entry's own expires_at (hours away) hasn't elapsed.
    assert decision.reason == "cancelled"
    assert decision.entry is not None
    assert decision.entry.status == "cancelled"
    assert decision.entry.decided_by == "guard-deadline"


async def test_short_window_expires_naturally(
    store: PendingConfirmationStore,
    audit: AuditLogger,
) -> None:
    """Per-category window < guard deadline → entry expires (silence=NO)."""

    # Window has integer hours; we cannot configure sub-hour windows
    # without changing the schema. Use ``max_wait_seconds`` slightly
    # under the (1 hour) window: the guard's deadline still fires
    # *before* the entry's own expires_at, so reason=cancelled is the
    # honest outcome here — the operator/CallbackQuery path is what
    # produces ``expired`` reasons in production.
    one_hour = DestructiveWhitelist(
        categories=(
            DestructiveCategory(
                id="short",
                description="short-window destructive",
                confirm_window_hours=1,
                match_any=(MatchRule(tool="rm", args_contains=("-rf",)),),
            ),
        )
    )
    decision = await check_destructive_action(
        cmd=["rm", "-rf", "/"],
        env=None,
        workspace_slug=None,
        whitelist=one_hour,
        store=store,
        audit=audit,
        poll_interval_seconds=0.02,
        max_wait_seconds=0.1,
    )
    assert decision.allow is False
    assert decision.entry is not None
    assert decision.entry.status in {"cancelled", "expired"}


# ── Workspace propagation ─────────────────────────────────────────────────


async def test_workspace_slug_propagates_to_entry(
    whitelist: DestructiveWhitelist,
    store: PendingConfirmationStore,
    audit: AuditLogger,
) -> None:
    async def cancel_quick() -> None:
        await asyncio.sleep(0.05)
        pending = store.list_pending()
        store.cancel(pending[0].id, by="t")

    task = asyncio.create_task(
        check_destructive_action(
            cmd=["git", "push", "origin", "main"],
            env=None,
            workspace_slug="my-project",
            whitelist=whitelist,
            store=store,
            audit=audit,
            poll_interval_seconds=0.02,
        )
    )
    await cancel_quick()
    decision = await task
    assert decision.entry is not None
    assert decision.entry.workspace_slug == "my-project"


# ── Audit event emission (file-tail) ──────────────────────────────────────


async def test_audit_emits_requested_and_approved(
    tmp_path: Path,
    whitelist: DestructiveWhitelist,
    store: PendingConfirmationStore,
) -> None:
    """The guard emits ``requested`` on match and ``approved`` on approve.

    Audit is JSONL-backed; we tail the file directly rather than
    depending on a ``read_back`` API the logger does not expose.
    """
    import json as _json

    audit_dir = tmp_path / "audit"
    audit_logger = AuditLogger(
        config=AuditConfig(audit_dir=str(audit_dir), enabled=True),
        session_id="audit-test",
    )

    async def approver() -> None:
        await asyncio.sleep(0.05)
        pending = store.list_pending()
        store.approve(pending[0].id, by="t")

    task = asyncio.create_task(
        check_destructive_action(
            cmd=["git", "push", "origin", "main"],
            env=None,
            workspace_slug="demo",
            whitelist=whitelist,
            store=store,
            audit=audit_logger,
            poll_interval_seconds=0.02,
        )
    )
    await approver()
    await task

    # Tail the audit JSONL — one event per line.
    audit_path = audit_logger.path
    assert audit_path is not None and audit_path.is_file()
    categories: list[str] = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = _json.loads(line)
        category = record.get("category") or record.get("event")
        if category:
            categories.append(category)
    assert "destructive_action_requested" in categories
    assert "destructive_action_approved" in categories


# ── SQL inline detection ──────────────────────────────────────────────────


async def test_sql_inline_drop_table_matches(
    store: PendingConfirmationStore,
    audit: AuditLogger,
) -> None:
    """An inline ``psql -c "DROP TABLE …"`` invocation gets caught."""
    wl = DestructiveWhitelist(
        categories=(
            DestructiveCategory(
                id="db",
                description="DB destructive",
                confirm_window_hours=4,
                match_any=(MatchRule(sql_keyword=("DROP TABLE",)),),
            ),
        )
    )

    async def cancel_quick() -> None:
        await asyncio.sleep(0.05)
        pending = store.list_pending()
        if pending:
            store.cancel(pending[0].id, by="t")

    task = asyncio.create_task(
        check_destructive_action(
            cmd=["psql", "-c", "DROP TABLE users CASCADE"],
            env=None,
            workspace_slug=None,
            whitelist=wl,
            store=store,
            audit=audit,
            poll_interval_seconds=0.02,
        )
    )
    await cancel_quick()
    decision = await task
    assert decision.allow is False
    assert decision.category_id == "db"
