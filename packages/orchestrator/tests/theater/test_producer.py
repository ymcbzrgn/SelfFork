"""Unit tests for :mod:`selffork_orchestrator.theater.producer` — S2 Theater.

Real SQLite (no mocks) for the store-backed producer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from selffork_orchestrator.theater.producer import (
    NullTheaterProducer,
    StoreTheaterProducer,
)
from selffork_orchestrator.theater.store import TheaterStore


@asynccontextmanager
async def _store(path: Path) -> AsyncIterator[TheaterStore]:
    s = TheaterStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


def _producer(store: TheaterStore) -> StoreTheaterProducer:
    return StoreTheaterProducer(
        store=store,
        session_id="sess-1",
        workspace_slug="proj-x",
        workspace_name="Project X",
        cli="claude",
    )


class TestStoreProducer:
    @pytest.mark.anyio
    async def test_loop_started_registers(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            await _producer(s).loop_started()
            active = await s.active_loop()
            assert active is not None
            assert active.session_id == "sess-1"
            assert active.cli == "claude"
            assert active.workspace_name == "Project X"

    @pytest.mark.anyio
    async def test_cli_output_appends_event(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            await _producer(s).cli_output("npm run dev\n", kind="stdout")
            events = await s.list_events("proj-x")
            assert len(events) == 1
            assert events[0].kind == "cli_output"
            assert events[0].payload == {
                "kind": "stdout",
                "text": "npm run dev\n",
            }

    @pytest.mark.anyio
    async def test_cli_output_default_kind_is_stdout(
        self, tmp_path: Path
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            await _producer(s).cli_output("hello")
            events = await s.list_events("proj-x")
            assert events[0].payload["kind"] == "stdout"

    @pytest.mark.anyio
    async def test_thought_emits_event_and_touches_loop(
        self, tmp_path: Path
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            p = _producer(s)
            await p.loop_started()
            await p.thought("I will test the login flow.", turn=3)
            events = await s.list_events("proj-x")
            assert len(events) == 1
            assert events[0].kind == "thought"
            assert events[0].payload["summary"] == (
                "I will test the login flow."
            )
            active = await s.active_loop()
            assert active is not None
            assert active.turn == 3
            assert active.last_thought == "I will test the login flow."

    @pytest.mark.anyio
    async def test_thought_without_narration_touches_turn_only(
        self, tmp_path: Path
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            p = _producer(s)
            await p.loop_started()
            # A pure tool-call reply parses to no thought.
            await p.thought(
                "<selffork-tool-call>{}</selffork-tool-call>", turn=5
            )
            assert await s.list_events("proj-x") == []
            active = await s.active_loop()
            assert active is not None
            assert active.turn == 5
            assert active.last_thought is None

    @pytest.mark.anyio
    async def test_loop_ended_clears(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            p = _producer(s)
            await p.loop_started()
            await p.loop_ended()
            assert await s.active_loop() is None


class TestResilience:
    @pytest.mark.anyio
    async def test_producer_swallows_store_errors(
        self, tmp_path: Path
    ) -> None:
        # A closed store raises on every call; the producer is
        # best-effort observability and must never crash the round-loop.
        s = TheaterStore(db_path=tmp_path / "t.db")
        await s.setup()
        await s.teardown()
        p = _producer(s)
        # None of these may raise.
        await p.loop_started()
        await p.cli_output("x")
        await p.thought("hello", turn=1)
        await p.loop_ended()


class TestNullProducer:
    @pytest.mark.anyio
    async def test_null_producer_is_inert(self) -> None:
        p = NullTheaterProducer()
        # No store, no error — every method is a no-op.
        await p.loop_started()
        await p.cli_output("x", kind="stderr")
        await p.thought("hello", turn=1)
        await p.loop_ended()
