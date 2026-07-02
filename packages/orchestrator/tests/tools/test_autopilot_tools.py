"""Tests for Jr autopilot act tools."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from selffork_mind.memory.model import Note
from selffork_mind.store import DuckDBMindStore
from selffork_orchestrator.resume.cron import LaunchdScheduler
from selffork_orchestrator.telegram.bridge import (
    DeliveryAttempt,
    NullTelegramBridge,
    TelegramBridge,
    TelegramMessage,
)
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
        mind_store=overrides.get("mind_store"),  # type: ignore[arg-type]
        launchd_scheduler=overrides.get("launchd_scheduler"),  # type: ignore[arg-type]
        resume_store=overrides.get("resume_store"),  # type: ignore[arg-type]
        telegram_bridge=overrides.get("telegram_bridge"),  # type: ignore[arg-type]
    )


@asynccontextmanager
async def _open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    store = DuckDBMindStore(db_path=path)
    await store.setup()
    try:
        yield store
    finally:
        await store.teardown()


class _FakeBridge(TelegramBridge):
    """Records the last message + returns a scripted delivery outcome."""

    def __init__(self, outcome: DeliveryAttempt) -> None:
        self._outcome = outcome
        self.sent: list[TelegramMessage] = []

    async def notify(self, message: TelegramMessage) -> DeliveryAttempt:
        self.sent.append(message)
        return self._outcome


class _RaisingBridge(TelegramBridge):
    """Bridge whose ``notify`` raises — the tool must degrade gracefully."""

    async def notify(self, message: TelegramMessage) -> DeliveryAttempt:
        del message
        msg = "telegram down"
        raise RuntimeError(msg)


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


@pytest.mark.anyio
async def test_notify_telegram_unwired_records_intent() -> None:
    """Without a bridge, the tool records intent (Order 5 stub shape)."""
    reg = _registry()
    result = await reg.invoke_async(
        ToolCall(
            tool="notify_telegram",
            args={"level": "warn", "message": "claude doluyor"},
            order_in_reply=0,
        ),
        _ctx(),
    )
    payload = result.payload or {}
    assert payload["delivered"] is False
    assert "not wired" in payload["reason"]
    assert payload["level"] == "warn"
    assert "claude doluyor" in payload["message_preview"]


@pytest.mark.anyio
async def test_notify_telegram_null_bridge_records_intent() -> None:
    """An explicit :class:`NullTelegramBridge` also counts as unwired."""
    reg = _registry()
    result = await reg.invoke_async(
        ToolCall(
            tool="notify_telegram",
            args={"level": "info", "message": "heartbeat"},
            order_in_reply=0,
        ),
        _ctx(telegram_bridge=NullTelegramBridge()),
    )
    payload = result.payload or {}
    assert payload["delivered"] is False
    assert "not wired" in payload["reason"]


@pytest.mark.anyio
async def test_notify_telegram_delivers_via_bridge() -> None:
    """Happy path — a wired bridge delivers and metadata surfaces."""
    sent_at = datetime.now(tz=UTC)
    bridge = _FakeBridge(
        DeliveryAttempt(delivered=True, chat_id=4242, sent_at=sent_at),
    )
    reg = _registry()
    result = await reg.invoke_async(
        ToolCall(
            tool="notify_telegram",
            args={"level": "crit", "message": "blocked: awaiting decision"},
            order_in_reply=0,
        ),
        _ctx(telegram_bridge=bridge, project_slug="proj-x"),
    )
    payload = result.payload or {}
    assert payload["delivered"] is True
    assert payload["chat_id"] == 4242
    assert payload["sent_at"] == sent_at.isoformat()
    assert payload["level"] == "crit"
    assert "blocked" in payload["message_preview"]
    # The bridge received the full message, level + scope intact.
    assert len(bridge.sent) == 1
    assert bridge.sent[0].level == "crit"
    assert bridge.sent[0].project_slug == "proj-x"
    assert bridge.sent[0].session_id == "session-1"


@pytest.mark.anyio
async def test_notify_telegram_bridge_raise_degrades_gracefully() -> None:
    """A bridge that raises must not crash the round loop."""
    reg = _registry()
    result = await reg.invoke_async(
        ToolCall(
            tool="notify_telegram",
            args={"level": "warn", "message": "will fail"},
            order_in_reply=0,
        ),
        _ctx(telegram_bridge=_RaisingBridge()),
    )
    assert result.status == "ok"  # handler swallowed the raise
    payload = result.payload or {}
    assert payload["delivered"] is False
    assert "telegram notify raised" in payload["reason"]
    assert "RuntimeError" in payload["reason"]
    assert "will fail" in payload["message_preview"]


# ── compact_context ───────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_compact_context_without_mind_returns_deferred_false() -> None:
    """Without mind_store wiring, the tool refuses to claim it ran."""
    reg = _registry()
    result = await reg.invoke_async(
        ToolCall(tool="compact_context", args={}, order_in_reply=0),
        _ctx(),
    )
    payload = result.payload or {}
    assert payload["compaction_requested"] is False
    assert "mind_store not wired" in payload["deferred"]


@pytest.mark.anyio
async def test_compact_context_non_store_object_returns_deferred_false() -> None:
    """A wired object that isn't a MindStore is refused, not crashed."""
    reg = _registry()
    result = await reg.invoke_async(
        ToolCall(tool="compact_context", args={}, order_in_reply=0),
        _ctx(mind_store=object()),
    )
    payload = result.payload or {}
    assert payload["compaction_requested"] is False
    assert "not a MindStore" in payload["deferred"]


@pytest.mark.anyio
async def test_compact_context_truncate_runs_recency(tmp_path: Path) -> None:
    """``truncate`` maps to L1 recency-decay and applies importance updates."""
    async with _open_store(tmp_path / "mind.duckdb") as store:
        await store.upsert_note(
            Note(
                tier="episodic",
                kind="observation",
                content="old round log that should decay",
                intent="",
                importance=8.0,
                valid_from=datetime.now(tz=UTC) - timedelta(days=14),
                project_slug="p1",
            ),
        )
        reg = _registry()
        result = await reg.invoke_async(
            ToolCall(
                tool="compact_context",
                args={"strategy": "truncate", "reason": "context full"},
                order_in_reply=0,
            ),
            _ctx(mind_store=store),
        )
    payload = result.payload or {}
    assert payload["compaction_requested"] is True
    assert payload["strategy"] == "truncate"
    assert payload["reason"] == "context full"
    assert payload["layer"] == "recency"
    assert payload["candidate_count"] >= 1
    assert payload["applied"]["importance_updates"] >= 1


@pytest.mark.anyio
async def test_compact_context_handoff_runs_distill(tmp_path: Path) -> None:
    """``handoff`` maps to L2 importance-distillation over the window."""
    async with _open_store(tmp_path / "mind.duckdb") as store:
        await store.upsert_note(
            Note(
                tier="episodic",
                kind="decision",
                content="we decided to lock the retrieval embedder",
                intent="lock the plan",
                importance=2.0,
                project_slug="p1",
            ),
        )
        reg = _registry()
        result = await reg.invoke_async(
            ToolCall(
                tool="compact_context",
                args={"strategy": "handoff", "reason": "rotating to codex"},
                order_in_reply=0,
            ),
            _ctx(mind_store=store),
        )
    payload = result.payload or {}
    assert payload["compaction_requested"] is True
    assert payload["strategy"] == "handoff"
    assert payload["reason"] == "rotating to codex"
    assert payload["layer"] == "distill"
    assert payload["candidate_count"] >= 1


@pytest.mark.anyio
async def test_compact_context_summary_runs_cluster(tmp_path: Path) -> None:
    """``summary`` maps to L3 medoid-clustering (Jaccard fallback here)."""
    # Two near-identical notes (Jaccard distance 0.2 < the 0.25 cutoff) so
    # they cluster; distinct trailing token keeps them separate rows (the
    # store is content-addressed and would otherwise dedupe them to one).
    async with _open_store(tmp_path / "mind.duckdb") as store:
        for suffix in ("today", "again"):
            await store.upsert_note(
                Note(
                    tier="episodic",
                    kind="observation",
                    content=f"the api uses the bge-m3 embedder for retrieval {suffix}",
                    intent="",
                    importance=3.0,
                    project_slug="p1",
                ),
            )
        reg = _registry()
        result = await reg.invoke_async(
            ToolCall(
                tool="compact_context",
                args={"strategy": "summary"},
                order_in_reply=0,
            ),
            _ctx(mind_store=store),
        )
    payload = result.payload or {}
    assert payload["compaction_requested"] is True
    assert payload["strategy"] == "summary"
    assert payload["layer"] == "cluster"
    assert payload["candidate_count"] == 2
    # The near-duplicate pair collapses: one member is superseded.
    assert payload["applied"]["cluster_supersede"] >= 1
