"""Unit tests for :mod:`selffork_orchestrator.talk.store` — S1 Talk Loop.

Real SQLite on tmp_path (no mocks). Each test opens a fresh store via the
``_store`` async context so teardown happens even on failure.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest

from selffork_orchestrator.talk.store import TalkStore
from selffork_shared.errors import ConfigError


@asynccontextmanager
async def _store(path: Path) -> AsyncIterator[TalkStore]:
    s = TalkStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


# ── Conversations ────────────────────────────────────────────────────────────


class TestConversation:
    @pytest.mark.anyio
    async def test_create_round_trip(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            c = await s.create_conversation(workspace_slug="proj-x", title="login flow")
            assert c.workspace_slug == "proj-x"
            assert c.title == "login flow"
            assert c.created_at == c.last_message_at

            fetched = await s.get_conversation(c.id)
            assert fetched is not None
            assert fetched.id == c.id

    @pytest.mark.anyio
    async def test_global_conversation_has_no_workspace(
        self,
        tmp_path: Path,
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            c = await s.create_conversation(workspace_slug=None, title="general")
            assert c.workspace_slug is None

    @pytest.mark.anyio
    async def test_empty_title_rejected(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            with pytest.raises(ConfigError):
                await s.create_conversation(workspace_slug=None, title="   ")

    @pytest.mark.anyio
    async def test_get_unknown_returns_none(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            assert await s.get_conversation(uuid4()) is None

    @pytest.mark.anyio
    async def test_append_promotes_conversation_in_list(
        self,
        tmp_path: Path,
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            first = await s.create_conversation(workspace_slug=None, title="first")
            second = await s.create_conversation(workspace_slug=None, title="second")
            # Appending to `first` makes it the most-recently-active.
            await s.append_message(conversation_id=first.id, role="operator", content="ping")
            listed = await s.list_conversations()
            assert listed[0].id == first.id
            assert {c.id for c in listed} == {first.id, second.id}


# ── Messages ─────────────────────────────────────────────────────────────────


class TestMessage:
    @pytest.mark.anyio
    async def test_append_round_trip(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            c = await s.create_conversation(workspace_slug=None, title="c")
            m = await s.append_message(conversation_id=c.id, role="operator", content="hello")
            assert m.seq == 1
            assert m.role == "operator"
            assert m.content == "hello"

    @pytest.mark.anyio
    async def test_seq_monotonic_per_conversation(
        self,
        tmp_path: Path,
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            c = await s.create_conversation(workspace_slug=None, title="c")
            m1 = await s.append_message(conversation_id=c.id, role="operator", content="m1")
            m2 = await s.append_message(conversation_id=c.id, role="self_jr", content="m2")
            m3 = await s.append_message(conversation_id=c.id, role="operator", content="m3")
            assert [m1.seq, m2.seq, m3.seq] == [1, 2, 3]

    @pytest.mark.anyio
    async def test_seq_independent_across_conversations(
        self,
        tmp_path: Path,
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            a = await s.create_conversation(workspace_slug=None, title="a")
            b = await s.create_conversation(workspace_slug=None, title="b")
            await s.append_message(conversation_id=a.id, role="operator", content="a1")
            b1 = await s.append_message(conversation_id=b.id, role="operator", content="b1")
            assert b1.seq == 1

    @pytest.mark.anyio
    async def test_append_bumps_last_message_at(
        self,
        tmp_path: Path,
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            c = await s.create_conversation(workspace_slug=None, title="c")
            m = await s.append_message(conversation_id=c.id, role="operator", content="hi")
            updated = await s.get_conversation(c.id)
            assert updated is not None
            assert updated.last_message_at == m.created_at

    @pytest.mark.anyio
    async def test_list_messages_in_seq_order(
        self,
        tmp_path: Path,
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            c = await s.create_conversation(workspace_slug=None, title="c")
            await s.append_message(conversation_id=c.id, role="operator", content="m1")
            await s.append_message(conversation_id=c.id, role="self_jr", content="m2")
            msgs = await s.list_messages(c.id)
            assert [m.content for m in msgs] == ["m1", "m2"]

    @pytest.mark.anyio
    async def test_list_messages_after_seq(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            c = await s.create_conversation(workspace_slug=None, title="c")
            await s.append_message(conversation_id=c.id, role="operator", content="m1")
            await s.append_message(conversation_id=c.id, role="self_jr", content="m2")
            delta = await s.list_messages_after(c.id, after_seq=1)
            assert [m.content for m in delta] == ["m2"]

    @pytest.mark.anyio
    async def test_empty_content_rejected(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            c = await s.create_conversation(workspace_slug=None, title="c")
            with pytest.raises(ConfigError):
                await s.append_message(conversation_id=c.id, role="operator", content="   ")

    @pytest.mark.anyio
    async def test_invalid_role_rejected(self, tmp_path: Path) -> None:
        async with _store(tmp_path / "t.db") as s:
            c = await s.create_conversation(workspace_slug=None, title="c")
            with pytest.raises(ConfigError):
                await s.append_message(
                    conversation_id=c.id,
                    role="banana",  # type: ignore[arg-type]
                    content="hi",
                )

    @pytest.mark.anyio
    async def test_append_to_unknown_conversation_rejected(
        self,
        tmp_path: Path,
    ) -> None:
        async with _store(tmp_path / "t.db") as s:
            with pytest.raises(ConfigError):
                await s.append_message(
                    conversation_id=uuid4(),
                    role="operator",
                    content="hi",
                )


# ── Persistence + guards ─────────────────────────────────────────────────────


class TestPersistence:
    @pytest.mark.anyio
    async def test_survives_store_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        async with _store(db) as s:
            c = await s.create_conversation(workspace_slug=None, title="c")
            await s.append_message(conversation_id=c.id, role="operator", content="persist me")
        # Fresh store, same file — history must survive the restart.
        async with _store(db) as s:
            msgs = await s.list_messages(c.id)
            assert [m.content for m in msgs] == ["persist me"]


class TestClosedStoreGuard:
    @pytest.mark.anyio
    async def test_writes_after_teardown_raise(self, tmp_path: Path) -> None:
        s = TalkStore(db_path=tmp_path / "t.db")
        await s.setup()
        await s.teardown()
        with pytest.raises(ConfigError):
            await s.create_conversation(workspace_slug=None, title="c")
