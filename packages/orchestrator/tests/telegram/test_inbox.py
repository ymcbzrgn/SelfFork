"""Tests for :class:`TelegramInbox`."""
from __future__ import annotations

from pathlib import Path

from selffork_orchestrator.telegram.inbox import TelegramInbox, default_inbox_path


def _inbox(tmp_path: Path) -> TelegramInbox:
    return TelegramInbox(tmp_path / "inbox.sqlite")


def test_default_inbox_path_under_home() -> None:
    assert default_inbox_path() == Path.home() / ".selffork" / "telegram-inbox.sqlite"


def test_initial_inbox_is_empty(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path)
    assert inbox.list_pending() == []


def test_add_persists_and_returns_record(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path)
    msg = inbox.add(chat_id=42, text="hello")
    assert msg.id > 0
    assert msg.chat_id == 42
    assert msg.text == "hello"
    assert msg.delivered is False


def test_list_pending_returns_in_receipt_order(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path)
    inbox.add(chat_id=1, text="first")
    inbox.add(chat_id=1, text="second")
    inbox.add(chat_id=1, text="third")
    msgs = inbox.list_pending()
    assert [m.text for m in msgs] == ["first", "second", "third"]


def test_mark_delivered_filters_pending(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path)
    a = inbox.add(chat_id=1, text="a")
    b = inbox.add(chat_id=1, text="b")
    c = inbox.add(chat_id=1, text="c")
    assert inbox.mark_delivered([a.id, b.id]) == 2
    pending = inbox.list_pending()
    assert [m.text for m in pending] == ["c"]
    assert pending[0].id == c.id


def test_mark_delivered_empty_iterable_is_zero(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path)
    inbox.add(chat_id=1, text="x")
    assert inbox.mark_delivered([]) == 0
    assert len(inbox.list_pending()) == 1


def test_mark_delivered_unknown_id_is_zero(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path)
    assert inbox.mark_delivered([999]) == 0


def test_clear_wipes_everything(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path)
    inbox.add(chat_id=1, text="x")
    inbox.add(chat_id=2, text="y")
    inbox.clear()
    assert inbox.list_pending() == []


def test_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "inbox.sqlite"
    a = TelegramInbox(path)
    a.add(chat_id=1, text="one")
    b = TelegramInbox(path)  # new instance, same DB
    pending = b.list_pending()
    assert len(pending) == 1
    assert pending[0].text == "one"
