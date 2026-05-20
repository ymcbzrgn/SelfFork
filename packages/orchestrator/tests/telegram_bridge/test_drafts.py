"""Tests for the Telegram draft queue (S3 Phase C/D)."""

from __future__ import annotations

from pathlib import Path

import pytest

from selffork_orchestrator.telegram.drafts import TelegramDraftStore


@pytest.fixture
def store(tmp_path: Path) -> TelegramDraftStore:
    return TelegramDraftStore(path=tmp_path / "drafts.sqlite")


def test_add_then_list(store: TelegramDraftStore) -> None:
    draft = store.add(chat_id=42, text="hello jr", sender="yamac")
    assert draft.id > 0
    assert draft.text == "hello jr"
    assert draft.sender == "yamac"
    assert not draft.claimed
    pending = store.list_unclaimed()
    assert [d.id for d in pending] == [draft.id]
    assert store.count_unclaimed() == 1


def test_claim_marks_delivered(store: TelegramDraftStore) -> None:
    a = store.add(chat_id=42, text="one", sender=None)
    b = store.add(chat_id=42, text="two", sender=None)
    affected = store.claim([a.id])
    assert affected == 1
    remaining = store.list_unclaimed()
    assert [d.id for d in remaining] == [b.id]


def test_claim_empty_ids_is_noop(store: TelegramDraftStore) -> None:
    assert store.claim([]) == 0


def test_clear_wipes_everything(store: TelegramDraftStore) -> None:
    store.add(chat_id=1, text="x", sender=None)
    store.add(chat_id=2, text="y", sender=None)
    store.clear()
    assert store.list_unclaimed() == []
    assert store.count_unclaimed() == 0


def test_persistence_across_reopen(tmp_path: Path) -> None:
    """A new store instance reads the same DB and sees prior drafts."""
    path = tmp_path / "drafts.sqlite"
    first = TelegramDraftStore(path=path)
    first.add(chat_id=10, text="hi", sender="op")
    second = TelegramDraftStore(path=path)
    drafts = second.list_unclaimed()
    assert len(drafts) == 1
    assert drafts[0].text == "hi"
