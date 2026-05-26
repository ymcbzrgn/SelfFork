"""Tests for the S-Bridge structured-question store + AskUserQuestion tool."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from selffork_orchestrator.tools.base import ToolContext
from selffork_orchestrator.tools.structured_question import (
    DEFAULT_STRUCTURED_QUESTION_TIMEOUT_SECONDS,
    AskUserQuestionArgs,
    PendingStructuredQuestion,
    PendingStructuredQuestionStore,
    SqlitePendingStructuredQuestionStore,
    build_ask_user_question_spec,
    build_structured_question_store,
    cleanup_loop,
    handle_ask_user_question,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _payload(
    question: str = "Pick one",
    *,
    multi: bool = False,
) -> dict[str, Any]:
    return {
        "questions": [
            {
                "question": question,
                "header": "Pick",
                "options": [
                    {"label": "Yes", "description": "do it"},
                    {"label": "No", "description": "don't do it"},
                ],
                "multiSelect": multi,
            },
        ],
    }


def _make_ctx(
    *,
    store: PendingStructuredQuestionStore | None = None,
    session_id: str = "s-test",
) -> ToolContext:
    return ToolContext(
        session_id=session_id,
        project_slug=None,
        project_store=object(),
        structured_question_store=store,
    )


# ── PendingStructuredQuestionStore ─────────────────────────────────────


@pytest.mark.asyncio
async def test_store_register_creates_entry() -> None:
    store = PendingStructuredQuestionStore()
    entry = await store.register(payload=_payload(), session_id="s-1")
    assert isinstance(entry, PendingStructuredQuestion)
    assert len(entry.correlation_id) == 8
    assert entry.session_id == "s-1"
    assert entry.event.is_set() is False
    assert entry.cancelled is False
    assert await store.get(entry.correlation_id) is entry


@pytest.mark.asyncio
async def test_store_register_assigns_distinct_correlation_ids() -> None:
    store = PendingStructuredQuestionStore()
    e1 = await store.register(payload=_payload())
    e2 = await store.register(payload=_payload())
    assert e1.correlation_id != e2.correlation_id


@pytest.mark.asyncio
async def test_store_submit_answer_round_trip() -> None:
    store = PendingStructuredQuestionStore()
    entry = await store.register(payload=_payload())

    async def _waiter() -> str | None:
        return await store.wait_for_answer(
            entry.correlation_id, timeout_seconds=2.0,
        )

    task = asyncio.create_task(_waiter())
    await asyncio.sleep(0.05)
    ok = await store.submit_answer(entry.correlation_id, "Yes")
    assert ok is True
    answer = await asyncio.wait_for(task, timeout=1.0)
    assert answer == "Yes"
    # Entry persists with answered metadata.
    stored = await store.get(entry.correlation_id)
    assert stored is not None
    assert stored.answer == "Yes"
    assert stored.answered_at is not None
    assert stored.event.is_set() is True


@pytest.mark.asyncio
async def test_store_submit_answer_idempotent() -> None:
    store = PendingStructuredQuestionStore()
    entry = await store.register(payload=_payload())
    assert await store.submit_answer(entry.correlation_id, "first") is True
    # Second submit MUST be a no-op (already resolved).
    assert await store.submit_answer(entry.correlation_id, "second") is False
    stored = await store.get(entry.correlation_id)
    assert stored is not None and stored.answer == "first"


@pytest.mark.asyncio
async def test_store_submit_unknown_correlation_returns_false() -> None:
    store = PendingStructuredQuestionStore()
    assert await store.submit_answer("nosuch", "Yes") is False


@pytest.mark.asyncio
async def test_store_cancel_wakes_waiter_without_answer() -> None:
    store = PendingStructuredQuestionStore()
    entry = await store.register(payload=_payload())

    async def _waiter() -> str | None:
        return await store.wait_for_answer(
            entry.correlation_id, timeout_seconds=2.0,
        )

    task = asyncio.create_task(_waiter())
    await asyncio.sleep(0.05)
    assert await store.cancel(entry.correlation_id) is True
    answer = await asyncio.wait_for(task, timeout=1.0)
    assert answer is None
    stored = await store.get(entry.correlation_id)
    assert stored is not None and stored.cancelled is True


@pytest.mark.asyncio
async def test_store_cancel_idempotent() -> None:
    store = PendingStructuredQuestionStore()
    entry = await store.register(payload=_payload())
    assert await store.cancel(entry.correlation_id) is True
    # Second cancel = no-op (event already set).
    assert await store.cancel(entry.correlation_id) is False


@pytest.mark.asyncio
async def test_store_wait_for_answer_timeout_returns_none() -> None:
    store = PendingStructuredQuestionStore()
    entry = await store.register(payload=_payload(), ttl_seconds=10.0)
    answer = await store.wait_for_answer(
        entry.correlation_id, timeout_seconds=0.1,
    )
    assert answer is None
    # Entry is NOT cancelled — just timed out.
    stored = await store.get(entry.correlation_id)
    assert stored is not None
    assert stored.cancelled is False
    assert stored.event.is_set() is False


@pytest.mark.asyncio
async def test_store_wait_for_unknown_correlation_returns_none() -> None:
    store = PendingStructuredQuestionStore()
    answer = await store.wait_for_answer("nosuch", timeout_seconds=0.1)
    assert answer is None


@pytest.mark.asyncio
async def test_store_list_pending_excludes_resolved() -> None:
    store = PendingStructuredQuestionStore()
    e1 = await store.register(payload=_payload("a"))
    e2 = await store.register(payload=_payload("b"))
    e3 = await store.register(payload=_payload("c"))
    await store.submit_answer(e2.correlation_id, "ans")
    await store.cancel(e3.correlation_id)
    pending = await store.list_pending()
    assert [p.correlation_id for p in pending] == [e1.correlation_id]


@pytest.mark.asyncio
async def test_store_cleanup_expired_removes_old_entries() -> None:
    store = PendingStructuredQuestionStore()
    entry = await store.register(payload=_payload(), ttl_seconds=5.0)
    # Manually set expires_at to the past to force cleanup.
    entry.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    removed = await store.cleanup_expired()
    assert removed == 1
    assert await store.get(entry.correlation_id) is None


@pytest.mark.asyncio
async def test_store_cleanup_wakes_pending_waiter() -> None:
    store = PendingStructuredQuestionStore()
    entry = await store.register(payload=_payload(), ttl_seconds=5.0)

    async def _waiter() -> str | None:
        return await store.wait_for_answer(
            entry.correlation_id, timeout_seconds=2.0,
        )

    task = asyncio.create_task(_waiter())
    await asyncio.sleep(0.05)
    entry.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await store.cleanup_expired()
    answer = await asyncio.wait_for(task, timeout=1.0)
    assert answer is None


# ── handle_ask_user_question (tool handler) ────────────────────────────


@pytest.mark.asyncio
async def test_handler_unwired_returns_status_unwired() -> None:
    ctx = _make_ctx(store=None)
    args = AskUserQuestionArgs.model_validate(_payload())
    result = await handle_ask_user_question(ctx, args)
    assert result["status"] == "unwired"
    assert result["correlation_id"] is None
    assert result["answer"] is None
    assert "not wired" in result["message"]


@pytest.mark.asyncio
async def test_handler_returns_answer_when_submitted() -> None:
    store = PendingStructuredQuestionStore()
    ctx = _make_ctx(store=store, session_id="s-handler")
    args = AskUserQuestionArgs.model_validate(_payload("Proceed?"))

    async def _resolver() -> None:
        # Poll for the pending entry, then submit.
        for _ in range(50):
            pending = await store.list_pending()
            if pending:
                await store.submit_answer(pending[0].correlation_id, "Yes")
                return
            await asyncio.sleep(0.02)

    resolver = asyncio.create_task(_resolver())
    try:
        result = await asyncio.wait_for(
            handle_ask_user_question(ctx, args), timeout=3.0,
        )
    finally:
        resolver.cancel()
    assert result["status"] == "answered"
    assert result["answer"] == "Yes"
    assert isinstance(result["correlation_id"], str)


@pytest.mark.asyncio
async def test_handler_returns_timeout_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "SELFFORK_STRUCTURED_QUESTION_TIMEOUT_SECONDS", "0.1",
    )
    store = PendingStructuredQuestionStore()
    ctx = _make_ctx(store=store)
    args = AskUserQuestionArgs.model_validate(_payload())
    result = await handle_ask_user_question(ctx, args)
    assert result["status"] == "timeout"
    assert result["answer"] is None
    assert "did not answer" in result["message"]


@pytest.mark.asyncio
async def test_handler_returns_cancelled_status() -> None:
    store = PendingStructuredQuestionStore()
    ctx = _make_ctx(store=store)
    args = AskUserQuestionArgs.model_validate(_payload())

    async def _cancel_after_register() -> None:
        for _ in range(50):
            pending = await store.list_pending()
            if pending:
                await store.cancel(pending[0].correlation_id)
                return
            await asyncio.sleep(0.02)

    cancel_task = asyncio.create_task(_cancel_after_register())
    try:
        result = await asyncio.wait_for(
            handle_ask_user_question(ctx, args), timeout=3.0,
        )
    finally:
        cancel_task.cancel()
    assert result["status"] == "cancelled"
    assert result["answer"] is None


@pytest.mark.asyncio
async def test_handler_clamps_low_timeout_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout < 5s is clamped to 5s floor."""
    monkeypatch.setenv(
        "SELFFORK_STRUCTURED_QUESTION_TIMEOUT_SECONDS", "0.001",
    )
    from selffork_orchestrator.tools.structured_question import (
        _resolve_timeout_seconds,
    )
    assert _resolve_timeout_seconds() == 5.0


def test_handler_default_timeout_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "SELFFORK_STRUCTURED_QUESTION_TIMEOUT_SECONDS", raising=False,
    )
    from selffork_orchestrator.tools.structured_question import (
        _resolve_timeout_seconds,
    )
    assert (
        _resolve_timeout_seconds()
        == DEFAULT_STRUCTURED_QUESTION_TIMEOUT_SECONDS
    )


def test_handler_default_timeout_when_env_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "SELFFORK_STRUCTURED_QUESTION_TIMEOUT_SECONDS", "not-a-number",
    )
    from selffork_orchestrator.tools.structured_question import (
        _resolve_timeout_seconds,
    )
    assert (
        _resolve_timeout_seconds()
        == DEFAULT_STRUCTURED_QUESTION_TIMEOUT_SECONDS
    )


# ── build_ask_user_question_spec (registration) ────────────────────────


def test_spec_name_matches_ask_user_question() -> None:
    spec = build_ask_user_question_spec()
    assert spec.name == "AskUserQuestion"
    assert spec.args_model is AskUserQuestionArgs


def test_spec_registered_in_default_registry() -> None:
    from selffork_orchestrator.tools import build_default_registry
    registry = build_default_registry()
    assert "AskUserQuestion" in registry.names()


@pytest.mark.asyncio
async def test_invoke_through_registry_returns_unwired_without_store() -> None:
    """Tool MUST be reachable from ToolRegistry.invoke_async."""
    from selffork_orchestrator.tools import build_default_registry
    from selffork_orchestrator.tools.base import ToolCall

    registry = build_default_registry()
    ctx = ToolContext(
        session_id="s",
        project_slug=None,
        project_store=object(),
    )
    call = ToolCall(
        tool="AskUserQuestion",
        args=_payload(),
        order_in_reply=0,
    )
    result = await registry.invoke_async(call, ctx)
    assert result.status == "ok"
    assert result.payload is not None
    assert result.payload["status"] == "unwired"


# ── cleanup_loop (S-ToolFleet Faz 0 F4) ────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_loop_purges_expired_entries() -> None:
    """First sweep on loop start removes already-expired entries."""
    store = PendingStructuredQuestionStore()
    entry = await store.register(payload=_payload(), ttl_seconds=5.0)
    entry.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert await store.get(entry.correlation_id) is not None

    task = asyncio.create_task(cleanup_loop(store, interval_seconds=10.0))
    # First sweep runs before the first sleep — give the event loop a tick.
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await store.get(entry.correlation_id) is None


@pytest.mark.asyncio
async def test_cleanup_loop_rejects_invalid_interval() -> None:
    store = PendingStructuredQuestionStore()
    with pytest.raises(ValueError):
        await cleanup_loop(store, interval_seconds=0)
    with pytest.raises(ValueError):
        await cleanup_loop(store, interval_seconds=-1.0)


@pytest.mark.asyncio
async def test_cleanup_loop_cancel_runs_final_sweep() -> None:
    """Cancellation triggers a final cleanup so shutdown drains expired."""
    store = PendingStructuredQuestionStore()
    # Long interval so the first sweep does NOT see the expired entry —
    # only the cancellation-time final sweep should catch it.
    task = asyncio.create_task(cleanup_loop(store, interval_seconds=10.0))
    await asyncio.sleep(0.05)  # let initial sweep land + enter sleep
    entry = await store.register(payload=_payload(), ttl_seconds=5.0)
    entry.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await store.get(entry.correlation_id) is None


# ── SqlitePendingStructuredQuestionStore (S-ToolFleet Faz 0 F2) ────────


@pytest.mark.asyncio
async def test_sqlite_store_register_round_trip(tmp_path: Path) -> None:
    """SQLite store persists an entry that ``get`` reads back."""
    store = SqlitePendingStructuredQuestionStore(
        db_path=tmp_path / "psq.db",
    )
    entry = await store.register(
        payload=_payload(question="Q?"), session_id="s1", ttl_seconds=60.0,
    )
    fetched = await store.get(entry.correlation_id)
    assert fetched is not None
    assert fetched.payload == _payload(question="Q?")
    assert fetched.session_id == "s1"
    assert fetched.answer is None
    assert fetched.cancelled is False


@pytest.mark.asyncio
async def test_sqlite_store_cross_process_handshake(tmp_path: Path) -> None:
    """Two store instances on the same DB act like one process pair.

    Simulates the cross-process gap fix: the CLI subprocess registers a
    pending question and polls; the dashboard process answers via a
    SEPARATE store instance (same DB path). The CLI-side waiter wakes.
    """
    db = tmp_path / "psq.db"
    cli_store = SqlitePendingStructuredQuestionStore(
        db_path=db, poll_interval_seconds=0.05,
    )
    dashboard_store = SqlitePendingStructuredQuestionStore(db_path=db)

    entry = await cli_store.register(payload=_payload(), ttl_seconds=30.0)

    async def _answer_after_delay() -> bool:
        await asyncio.sleep(0.1)
        return await dashboard_store.submit_answer(
            entry.correlation_id, "codex",
        )

    answer_task = asyncio.create_task(_answer_after_delay())
    answer = await cli_store.wait_for_answer(
        entry.correlation_id, timeout_seconds=5.0,
    )
    assert answer == "codex"
    assert await answer_task is True


@pytest.mark.asyncio
async def test_sqlite_store_wait_for_answer_timeout(tmp_path: Path) -> None:
    store = SqlitePendingStructuredQuestionStore(
        db_path=tmp_path / "psq.db", poll_interval_seconds=0.05,
    )
    entry = await store.register(payload=_payload(), ttl_seconds=30.0)
    answer = await store.wait_for_answer(
        entry.correlation_id, timeout_seconds=0.2,
    )
    assert answer is None


@pytest.mark.asyncio
async def test_sqlite_store_cancel_wakes_waiter(tmp_path: Path) -> None:
    db = tmp_path / "psq.db"
    cli_store = SqlitePendingStructuredQuestionStore(
        db_path=db, poll_interval_seconds=0.05,
    )
    dashboard_store = SqlitePendingStructuredQuestionStore(db_path=db)
    entry = await cli_store.register(payload=_payload(), ttl_seconds=30.0)

    async def _cancel_after_delay() -> bool:
        await asyncio.sleep(0.1)
        return await dashboard_store.cancel(entry.correlation_id)

    cancel_task = asyncio.create_task(_cancel_after_delay())
    answer = await cli_store.wait_for_answer(
        entry.correlation_id, timeout_seconds=5.0,
    )
    assert answer is None
    assert await cancel_task is True

    fetched = await cli_store.get(entry.correlation_id)
    assert fetched is not None
    assert fetched.cancelled is True


@pytest.mark.asyncio
async def test_sqlite_store_submit_idempotent(tmp_path: Path) -> None:
    store = SqlitePendingStructuredQuestionStore(
        db_path=tmp_path / "psq.db",
    )
    entry = await store.register(payload=_payload(), ttl_seconds=60.0)
    assert await store.submit_answer(entry.correlation_id, "first") is True
    assert await store.submit_answer(entry.correlation_id, "second") is False
    fetched = await store.get(entry.correlation_id)
    assert fetched is not None
    assert fetched.answer == "first"


@pytest.mark.asyncio
async def test_sqlite_store_submit_unknown_correlation(tmp_path: Path) -> None:
    store = SqlitePendingStructuredQuestionStore(
        db_path=tmp_path / "psq.db",
    )
    assert await store.submit_answer("00000000", "x") is False
    assert await store.cancel("00000000") is False


@pytest.mark.asyncio
async def test_sqlite_store_list_pending_excludes_resolved(
    tmp_path: Path,
) -> None:
    store = SqlitePendingStructuredQuestionStore(
        db_path=tmp_path / "psq.db",
    )
    e1 = await store.register(payload=_payload(question="A?"))
    e2 = await store.register(payload=_payload(question="B?"))
    e3 = await store.register(payload=_payload(question="C?"))
    await store.submit_answer(e1.correlation_id, "a-answer")
    await store.cancel(e3.correlation_id)

    pending = await store.list_pending()
    pending_ids = {p.correlation_id for p in pending}
    assert pending_ids == {e2.correlation_id}


@pytest.mark.asyncio
async def test_sqlite_store_cleanup_removes_expired_only(
    tmp_path: Path,
) -> None:
    store = SqlitePendingStructuredQuestionStore(
        db_path=tmp_path / "psq.db",
    )
    expired = await store.register(payload=_payload(), ttl_seconds=60.0)
    fresh = await store.register(payload=_payload(), ttl_seconds=60.0)
    answered = await store.register(payload=_payload(), ttl_seconds=60.0)
    await store.submit_answer(answered.correlation_id, "x")

    # Force one entry's expires_at into the past via direct DB poke —
    # mirrors what wall-clock would do; faster than sleeping.
    import sqlite3 as _sqlite3
    from contextlib import closing as _closing

    past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    with _closing(_sqlite3.connect(tmp_path / "psq.db")) as conn:
        conn.execute(
            "UPDATE pending_structured_questions SET expires_at = ? "
            "WHERE correlation_id = ?",
            (past, expired.correlation_id),
        )
        conn.commit()

    removed = await store.cleanup_expired()
    assert removed == 1
    assert await store.get(expired.correlation_id) is None
    assert await store.get(fresh.correlation_id) is not None
    # Answered entries stay (audit trail) — cleanup only purges
    # unanswered + uncancelled expired rows.
    assert await store.get(answered.correlation_id) is not None


@pytest.mark.asyncio
async def test_sqlite_store_rejects_invalid_poll_interval(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        SqlitePendingStructuredQuestionStore(
            db_path=tmp_path / "psq.db", poll_interval_seconds=0,
        )
    with pytest.raises(ValueError):
        SqlitePendingStructuredQuestionStore(
            db_path=tmp_path / "psq.db", poll_interval_seconds=-0.1,
        )


@pytest.mark.asyncio
async def test_cleanup_loop_works_with_sqlite_store(tmp_path: Path) -> None:
    """cleanup_loop is store-shape-agnostic — pin it for SQLite too."""
    store = SqlitePendingStructuredQuestionStore(
        db_path=tmp_path / "psq.db",
    )
    entry = await store.register(payload=_payload(), ttl_seconds=60.0)

    past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    import sqlite3 as _sqlite3
    from contextlib import closing as _closing
    with _closing(_sqlite3.connect(tmp_path / "psq.db")) as conn:
        conn.execute(
            "UPDATE pending_structured_questions SET expires_at = ? "
            "WHERE correlation_id = ?",
            (past, entry.correlation_id),
        )
        conn.commit()

    task = asyncio.create_task(cleanup_loop(store, interval_seconds=10.0))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await store.get(entry.correlation_id) is None


# ── build_structured_question_store factory ────────────────────────────


def test_factory_returns_in_memory_when_no_path() -> None:
    store = build_structured_question_store()
    assert isinstance(store, PendingStructuredQuestionStore)
    assert not isinstance(store, SqlitePendingStructuredQuestionStore)


def test_factory_returns_sqlite_when_explicit_path(tmp_path: Path) -> None:
    store = build_structured_question_store(db_path=tmp_path / "x.db")
    assert isinstance(store, SqlitePendingStructuredQuestionStore)


def test_factory_resolves_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "from-env.db"
    monkeypatch.setenv("SELFFORK_STRUCTURED_QUESTION_DB", str(target))
    store = build_structured_question_store()
    assert isinstance(store, SqlitePendingStructuredQuestionStore)


def test_factory_explicit_overrides_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit ``db_path`` wins over the env var."""
    env_target = tmp_path / "env.db"
    explicit_target = tmp_path / "explicit.db"
    monkeypatch.setenv("SELFFORK_STRUCTURED_QUESTION_DB", str(env_target))
    store = build_structured_question_store(db_path=explicit_target)
    assert isinstance(store, SqlitePendingStructuredQuestionStore)
    # Touch the store so the schema is created and we can confirm path
    # — explicit_target was used, not env_target.
    asyncio.run(store._ensure_setup())
    assert explicit_target.exists()
    assert not env_target.exists()


def test_factory_empty_env_returns_in_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SELFFORK_STRUCTURED_QUESTION_DB", "   ")
    store = build_structured_question_store()
    assert isinstance(store, PendingStructuredQuestionStore)


def test_factory_unset_env_returns_in_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SELFFORK_STRUCTURED_QUESTION_DB", raising=False)
    store = build_structured_question_store()
    assert isinstance(store, PendingStructuredQuestionStore)
