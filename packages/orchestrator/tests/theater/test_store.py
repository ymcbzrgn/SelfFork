"""Unit tests for :mod:`selffork_orchestrator.theater.store` — S2 Theater.

Real SQLite on tmp_path (no mocks). Each test opens a fresh store via the
``_store`` async context so teardown happens even on failure.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from selffork_orchestrator.theater.store import TheaterStore
from selffork_shared.errors import ConfigError


@asynccontextmanager
async def _store(path: Path) -> AsyncIterator[TheaterStore]:
    s = TheaterStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


def _cli(text: str, kind: str = "stdout") -> dict[str, object]:
    return {"kind": kind, "text": text}


def _thought(summary: str, raw: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"summary": summary}
    if raw is not None:
        payload["raw"] = raw
    return payload


# ── Append ───────────────────────────────────────────────────────────────────


class TestAppendEvent:
    @pytest.mark.anyio
    async def test_cli_output_round_trip(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            ev = await s.append_event(
                workspace_slug="proj-x",
                session_id="sess-1",
                kind="cli_output",
                payload=_cli("npm run dev"),
            )
            assert ev.seq == 1
            assert ev.kind == "cli_output"
            assert ev.workspace_slug == "proj-x"
            assert ev.session_id == "sess-1"
            assert ev.payload == {"kind": "stdout", "text": "npm run dev"}

    @pytest.mark.anyio
    async def test_thought_round_trip(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            ev = await s.append_event(
                workspace_slug="proj-x",
                session_id="sess-1",
                kind="thought",
                payload=_thought("Testing the login flow", raw="<raw>"),
            )
            assert ev.kind == "thought"
            assert ev.payload == {
                "summary": "Testing the login flow",
                "raw": "<raw>",
            }

    @pytest.mark.anyio
    async def test_session_id_optional(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            ev = await s.append_event(
                workspace_slug="proj-x",
                session_id=None,
                kind="cli_output",
                payload=_cli("hello"),
            )
            assert ev.session_id is None

    @pytest.mark.anyio
    async def test_seq_monotonic_per_workspace(
        self, tmp_path: Path
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            e1 = await s.append_event(
                workspace_slug="px",
                session_id=None,
                kind="cli_output",
                payload=_cli("1"),
            )
            e2 = await s.append_event(
                workspace_slug="px",
                session_id=None,
                kind="thought",
                payload=_thought("2"),
            )
            e3 = await s.append_event(
                workspace_slug="px",
                session_id=None,
                kind="cli_output",
                payload=_cli("3"),
            )
            assert [e1.seq, e2.seq, e3.seq] == [1, 2, 3]

    @pytest.mark.anyio
    async def test_seq_independent_across_workspaces(
        self, tmp_path: Path
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            await s.append_event(
                workspace_slug="px",
                session_id=None,
                kind="cli_output",
                payload=_cli("a"),
            )
            first_b = await s.append_event(
                workspace_slug="py",
                session_id=None,
                kind="cli_output",
                payload=_cli("b"),
            )
            assert first_b.seq == 1


# ── List ─────────────────────────────────────────────────────────────────────


class TestListEvents:
    @pytest.mark.anyio
    async def test_list_in_seq_order(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            await s.append_event(
                workspace_slug="px",
                session_id=None,
                kind="cli_output",
                payload=_cli("first"),
            )
            await s.append_event(
                workspace_slug="px",
                session_id=None,
                kind="thought",
                payload=_thought("second"),
            )
            events = await s.list_events("px")
            assert [e.seq for e in events] == [1, 2]
            assert [e.kind for e in events] == ["cli_output", "thought"]

    @pytest.mark.anyio
    async def test_list_scoped_to_workspace(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            await s.append_event(
                workspace_slug="px",
                session_id=None,
                kind="cli_output",
                payload=_cli("x"),
            )
            await s.append_event(
                workspace_slug="py",
                session_id=None,
                kind="cli_output",
                payload=_cli("y"),
            )
            assert len(await s.list_events("px")) == 1
            assert len(await s.list_events("py")) == 1

    @pytest.mark.anyio
    async def test_list_events_after_seq(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            for n in range(1, 4):
                await s.append_event(
                    workspace_slug="px",
                    session_id=None,
                    kind="cli_output",
                    payload=_cli(f"m{n}"),
                )
            delta = await s.list_events_after("px", after_seq=1)
            assert [e.seq for e in delta] == [2, 3]
            whole = await s.list_events_after("px", after_seq=0)
            assert [e.seq for e in whole] == [1, 2, 3]

    @pytest.mark.anyio
    async def test_list_respects_limit(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            for n in range(5):
                await s.append_event(
                    workspace_slug="px",
                    session_id=None,
                    kind="cli_output",
                    payload=_cli(str(n)),
                )
            assert len(await s.list_events("px", limit=2)) == 2

    @pytest.mark.anyio
    async def test_list_empty_workspace(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            assert await s.list_events("never-used") == []


# ── Validation ───────────────────────────────────────────────────────────────


class TestValidation:
    @pytest.mark.anyio
    async def test_empty_workspace_slug_rejected(
        self, tmp_path: Path
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            with pytest.raises(ConfigError):
                await s.append_event(
                    workspace_slug="   ",
                    session_id=None,
                    kind="cli_output",
                    payload=_cli("x"),
                )

    @pytest.mark.anyio
    async def test_unknown_kind_rejected(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            with pytest.raises(ConfigError):
                await s.append_event(
                    workspace_slug="px",
                    session_id=None,
                    kind="banana",  # type: ignore[arg-type]
                    payload=_cli("x"),
                )

    @pytest.mark.anyio
    async def test_malformed_cli_payload_rejected(
        self, tmp_path: Path
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            with pytest.raises(ConfigError):
                # missing the required ``text`` field
                await s.append_event(
                    workspace_slug="px",
                    session_id=None,
                    kind="cli_output",
                    payload={"kind": "stdout"},
                )

    @pytest.mark.anyio
    async def test_malformed_thought_payload_rejected(
        self, tmp_path: Path
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            with pytest.raises(ConfigError):
                # unknown field — payload models forbid extras
                await s.append_event(
                    workspace_slug="px",
                    session_id=None,
                    kind="thought",
                    payload={"summary": "ok", "bogus": 1},
                )


# ── Persistence + guards ─────────────────────────────────────────────────────


class TestPersistence:
    @pytest.mark.anyio
    async def test_survives_store_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        async with _store(db) as s:
            await s.append_event(
                workspace_slug="px",
                session_id="s1",
                kind="cli_output",
                payload=_cli("persist me"),
            )
        # Fresh store, same file — the stream must survive the restart.
        async with _store(db) as s:
            events = await s.list_events("px")
            assert [e.payload["text"] for e in events] == ["persist me"]


class TestClosedStoreGuard:
    @pytest.mark.anyio
    async def test_writes_after_teardown_raise(
        self, tmp_path: Path
    ) -> None:
        s = TheaterStore(db_path=tmp_path / "t.db")
        await s.setup()
        await s.teardown()
        with pytest.raises(ConfigError):
            await s.append_event(
                workspace_slug="px",
                session_id=None,
                kind="cli_output",
                payload=_cli("x"),
            )


# ── Active loops ─────────────────────────────────────────────────────────────


class TestActiveLoop:
    @pytest.mark.anyio
    async def test_register_round_trip(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            rec = await s.register_loop(
                session_id="sess-1",
                workspace_slug="proj-x",
                workspace_name="Project X",
                cli="claude",
            )
            assert rec.turn == 0
            assert rec.last_thought is None
            active = await s.active_loop()
            assert active is not None
            assert active.session_id == "sess-1"
            assert active.cli == "claude"
            assert active.workspace_name == "Project X"

    @pytest.mark.anyio
    async def test_active_loop_none_when_idle(
        self, tmp_path: Path
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            assert await s.active_loop() is None

    @pytest.mark.anyio
    async def test_touch_advances_turn(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            await s.register_loop(
                session_id="s1",
                workspace_slug="px",
                workspace_name="PX",
                cli="claude",
            )
            await s.touch_loop(session_id="s1", turn=4)
            active = await s.active_loop()
            assert active is not None
            assert active.turn == 4

    @pytest.mark.anyio
    async def test_touch_sets_last_thought(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            await s.register_loop(
                session_id="s1",
                workspace_slug="px",
                workspace_name="PX",
                cli="claude",
            )
            await s.touch_loop(
                session_id="s1", turn=1, last_thought="Testing login"
            )
            active = await s.active_loop()
            assert active is not None
            assert active.last_thought == "Testing login"

    @pytest.mark.anyio
    async def test_touch_without_thought_keeps_previous(
        self, tmp_path: Path
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            await s.register_loop(
                session_id="s1",
                workspace_slug="px",
                workspace_name="PX",
                cli="claude",
            )
            await s.touch_loop(
                session_id="s1", turn=1, last_thought="first thought"
            )
            await s.touch_loop(session_id="s1", turn=2)
            active = await s.active_loop()
            assert active is not None
            assert active.turn == 2
            assert active.last_thought == "first thought"

    @pytest.mark.anyio
    async def test_clear_removes_loop(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            await s.register_loop(
                session_id="s1",
                workspace_slug="px",
                workspace_name="PX",
                cli="claude",
            )
            await s.clear_loop("s1")
            assert await s.active_loop() is None

    @pytest.mark.anyio
    async def test_loop_for_workspace(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            await s.register_loop(
                session_id="s1",
                workspace_slug="px",
                workspace_name="PX",
                cli="claude",
            )
            assert await s.loop_for_workspace("px") is not None
            assert await s.loop_for_workspace("py") is None

    @pytest.mark.anyio
    async def test_active_loop_picks_latest_touched(
        self, tmp_path: Path
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            await s.register_loop(
                session_id="s1",
                workspace_slug="px",
                workspace_name="PX",
                cli="claude",
            )
            await s.register_loop(
                session_id="s2",
                workspace_slug="py",
                workspace_name="PY",
                cli="gemini",
            )
            await s.touch_loop(session_id="s1", turn=1)
            active = await s.active_loop()
            assert active is not None
            assert active.session_id == "s1"

    @pytest.mark.anyio
    async def test_stale_loop_excluded(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            await s.register_loop(
                session_id="s1",
                workspace_slug="px",
                workspace_name="PX",
                cli="claude",
            )
            # Threshold 0 — the row's updated_at is already in the past.
            assert await s.active_loop(stale_after_seconds=0) is None
            assert (
                await s.loop_for_workspace("px", stale_after_seconds=0)
            ) is None

    @pytest.mark.anyio
    async def test_empty_session_id_rejected(
        self, tmp_path: Path
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            with pytest.raises(ConfigError):
                await s.register_loop(
                    session_id="  ",
                    workspace_slug="px",
                    workspace_name="PX",
                    cli="claude",
                )

    @pytest.mark.anyio
    async def test_loop_survives_store_reopen(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "t.db"
        async with _store(db) as s:
            await s.register_loop(
                session_id="s1",
                workspace_slug="px",
                workspace_name="PX",
                cli="claude",
            )
            await s.touch_loop(session_id="s1", turn=7)
        # Fresh store, same file — the dashboard process reads what a
        # separate run process wrote.
        async with _store(db) as s:
            active = await s.active_loop()
            assert active is not None
            assert active.turn == 7
