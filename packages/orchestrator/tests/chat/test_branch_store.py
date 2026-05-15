"""Unit tests for :mod:`selffork_orchestrator.chat.branch_store` — Order 4.

Real SQLite on tmp_path (no mocks). Each test opens a fresh store via
the ``open_branch_store`` async context so teardown happens even on
failure.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest

from selffork_orchestrator.chat.branch_store import BranchStore
from selffork_shared.errors import ConfigError


@asynccontextmanager
async def _store(path: Path) -> AsyncIterator[BranchStore]:
    s = BranchStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


# ── Branch lifecycle ─────────────────────────────────────────────────────────


class TestCreateBranch:
    @pytest.mark.anyio
    async def test_first_branch_becomes_active(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "b.db") as s:
            b = await s.create_branch(session_id="sess", label="main")
            assert b.is_active is True

            active = await s.get_active_branch("sess")
            assert active is not None and active.id == b.id

    @pytest.mark.anyio
    async def test_creating_active_branch_deactivates_previous(
        self,
        tmp_path: Path,
    ) -> None:
        async with _store(tmp_path / "b.db") as s:
            first = await s.create_branch(session_id="sess", label="main")
            second = await s.create_branch(
                session_id="sess",
                label="alt-1",
                parent_branch_id=first.id,
            )
            assert second.is_active is True

            branches = await s.list_branches("sess")
            actives = [b for b in branches if b.is_active]
            assert len(actives) == 1
            assert actives[0].id == second.id

    @pytest.mark.anyio
    async def test_inactive_branch_stays_inactive(
        self,
        tmp_path: Path,
    ) -> None:
        async with _store(tmp_path / "b.db") as s:
            first = await s.create_branch(session_id="sess", label="main")
            inactive = await s.create_branch(
                session_id="sess",
                label="archive",
                parent_branch_id=first.id,
                activate=False,
            )
            assert inactive.is_active is False
            assert (await s.get_active_branch("sess")).id == first.id  # type: ignore[union-attr]

    @pytest.mark.anyio
    async def test_empty_label_rejected(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "b.db") as s:
            with pytest.raises(ConfigError):
                await s.create_branch(session_id="sess", label="   ")


class TestSetActiveBranch:
    @pytest.mark.anyio
    async def test_switch_active_flag(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "b.db") as s:
            first = await s.create_branch(session_id="sess", label="main")
            alt = await s.create_branch(
                session_id="sess",
                label="alt",
                parent_branch_id=first.id,
                activate=False,
            )
            assert (await s.get_active_branch("sess")).id == first.id  # type: ignore[union-attr]
            await s.set_active_branch("sess", alt.id)
            assert (await s.get_active_branch("sess")).id == alt.id  # type: ignore[union-attr]

    @pytest.mark.anyio
    async def test_unknown_branch_raises(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "b.db") as s:
            await s.create_branch(session_id="sess", label="main")
            with pytest.raises(ConfigError):
                await s.set_active_branch("sess", uuid4())

    @pytest.mark.anyio
    async def test_cross_session_set_rejected(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "b.db") as s:
            in_a = await s.create_branch(session_id="A", label="main")
            await s.create_branch(session_id="B", label="main")
            with pytest.raises(ConfigError):
                await s.set_active_branch("B", in_a.id)


# ── Messages ─────────────────────────────────────────────────────────────────


class TestAppendMessage:
    @pytest.mark.anyio
    async def test_round_trip(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "b.db") as s:
            b = await s.create_branch(session_id="sess", label="main")
            m = await s.append_message(
                branch_id=b.id,
                role="user",
                content="hello",
            )
            fetched = await s.get_message(m.id)
            assert fetched is not None
            assert fetched.content == "hello"
            assert fetched.role == "user"

    @pytest.mark.anyio
    async def test_empty_content_rejected(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "b.db") as s:
            b = await s.create_branch(session_id="sess", label="main")
            with pytest.raises(ConfigError):
                await s.append_message(
                    branch_id=b.id,
                    role="user",
                    content="   ",
                )

    @pytest.mark.anyio
    async def test_invalid_role_rejected(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "b.db") as s:
            b = await s.create_branch(session_id="sess", label="main")
            with pytest.raises(ConfigError):
                await s.append_message(
                    branch_id=b.id,
                    role="banana",  # type: ignore[arg-type]
                    content="hi",
                )

    @pytest.mark.anyio
    async def test_list_messages_in_order(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "b.db") as s:
            b = await s.create_branch(session_id="sess", label="main")
            await s.append_message(branch_id=b.id, role="user", content="m1")
            await s.append_message(branch_id=b.id, role="assistant", content="m2")
            await s.append_message(branch_id=b.id, role="user", content="m3")
            msgs = await s.list_messages(b.id)
            assert [m.content for m in msgs] == ["m1", "m2", "m3"]


# ── Fork from message ────────────────────────────────────────────────────────


class TestForkFromMessage:
    @pytest.mark.anyio
    async def test_creates_branch_with_prefix(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "b.db") as s:
            main = await s.create_branch(session_id="sess", label="main")
            m1 = await s.append_message(
                branch_id=main.id,
                role="user",
                content="m1",
            )
            await s.append_message(branch_id=main.id, role="assistant", content="m2")
            await s.append_message(branch_id=main.id, role="user", content="m3")

            new_branch, prefix = await s.fork_from_message(
                session_id="sess",
                message_id=m1.id,
                label="alt-1",
            )
            assert new_branch.parent_branch_id == main.id
            assert new_branch.fork_message_id == m1.id
            assert [m.content for m in prefix] == ["m1"]
            # New branch has the same prefix; main untouched.
            new_msgs = await s.list_messages(new_branch.id)
            main_msgs = await s.list_messages(main.id)
            assert [m.content for m in new_msgs] == ["m1"]
            assert [m.content for m in main_msgs] == ["m1", "m2", "m3"]

    @pytest.mark.anyio
    async def test_unknown_message_raises(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "b.db") as s:
            await s.create_branch(session_id="sess", label="main")
            with pytest.raises(ConfigError):
                await s.fork_from_message(
                    session_id="sess",
                    message_id=uuid4(),
                    label="alt",
                )

    @pytest.mark.anyio
    async def test_cross_session_fork_rejected(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "b.db") as s:
            a_main = await s.create_branch(session_id="A", label="main")
            in_a = await s.append_message(
                branch_id=a_main.id,
                role="user",
                content="a",
            )
            await s.create_branch(session_id="B", label="main")
            with pytest.raises(ConfigError):
                await s.fork_from_message(
                    session_id="B",
                    message_id=in_a.id,
                    label="x",
                )


# ── Closed-store guard ───────────────────────────────────────────────────────


class TestClosedStoreGuard:
    @pytest.mark.anyio
    async def test_writes_after_teardown_raise(self, tmp_path: Path) -> None:
        s = BranchStore(db_path=tmp_path / "b.db")
        await s.setup()
        await s.teardown()
        with pytest.raises(ConfigError):
            await s.create_branch(session_id="sess", label="main")
