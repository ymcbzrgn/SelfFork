"""Tests for :class:`PtbTelegramBridge`."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from selffork_orchestrator.telegram.allowlist import AllowList
from selffork_orchestrator.telegram.bridge import TelegramMessage
from selffork_orchestrator.telegram.ptb import (
    PtbTelegramBridge,
    _format_message,
)


def test_init_rejects_empty_token() -> None:
    with pytest.raises(ValueError, match="non-empty bot_token"):
        PtbTelegramBridge(bot_token="", allowlist=AllowList())


def test_format_message_includes_level_and_session() -> None:
    text = _format_message(
        TelegramMessage(level="warn", text="claude doluyor", session_id="abc-123"),
    )
    assert "[warn]" in text
    assert "abc-123" in text
    assert "claude doluyor" in text


def test_format_message_html_escapes_text() -> None:
    text = _format_message(
        TelegramMessage(level="info", text="<script>alert(1)</script>", session_id="s"),
    )
    assert "&lt;script&gt;" in text
    assert "<script>" not in text


def test_format_message_truncates_long_text() -> None:
    text = _format_message(
        TelegramMessage(level="info", text="x" * 5000, session_id="s"),
    )
    assert "[truncated]" in text
    assert len(text) <= 4000


def test_format_message_includes_project_when_present() -> None:
    text = _format_message(
        TelegramMessage(
            level="crit",
            text="rate limit",
            session_id="s",
            project_slug="demo",
        ),
    )
    assert "demo" in text


def test_format_message_omits_project_when_absent() -> None:
    text = _format_message(
        TelegramMessage(level="info", text="x", session_id="s"),
    )
    assert "<code>s</code>" in text


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_notify_returns_undelivered_when_allowlist_empty() -> None:
    bridge = PtbTelegramBridge(
        bot_token="123:fake",
        allowlist=AllowList(),
    )
    attempt = await bridge.notify(
        TelegramMessage(level="info", text="hi", session_id="s"),
    )
    assert attempt.delivered is False
    assert "empty operator allowlist" in (attempt.reason or "")


@pytest.mark.anyio
async def test_notify_calls_send_message_per_allowlisted_chat() -> None:
    bridge = PtbTelegramBridge(
        bot_token="123:fake",
        allowlist=AllowList(chat_ids=frozenset({111, 222})),
    )
    fake_send = AsyncMock(return_value=None)
    with patch.object(bridge, "_send_one", fake_send):
        attempt = await bridge.notify(
            TelegramMessage(level="info", text="hello", session_id="s"),
        )
    assert attempt.delivered is True
    assert attempt.chat_id in {111, 222}
    assert fake_send.await_count == 2


@pytest.mark.anyio
async def test_notify_swallows_per_chat_telegram_errors() -> None:
    from telegram.error import TelegramError

    bridge = PtbTelegramBridge(
        bot_token="123:fake",
        allowlist=AllowList(chat_ids=frozenset({111, 222})),
    )

    async def _flaky(**kwargs: Any) -> None:
        if kwargs["chat_id"] == 111:
            raise TelegramError("forbidden")

    with patch.object(bridge, "_send_one", side_effect=_flaky):
        attempt = await bridge.notify(
            TelegramMessage(level="warn", text="x", session_id="s"),
        )
    # 222 succeeded → delivered True, but reason still surfaces 111 error.
    assert attempt.delivered is True
    assert attempt.chat_id == 222
    assert attempt.reason is not None
    assert "111" in attempt.reason


@pytest.mark.anyio
async def test_notify_returns_undelivered_when_all_chats_fail() -> None:
    from telegram.error import TelegramError

    bridge = PtbTelegramBridge(
        bot_token="123:fake",
        allowlist=AllowList(chat_ids=frozenset({111})),
    )
    with patch.object(
        bridge,
        "_send_one",
        side_effect=TelegramError("boom"),
    ):
        attempt = await bridge.notify(
            TelegramMessage(level="crit", text="x", session_id="s"),
        )
    assert attempt.delivered is False
    assert "boom" in (attempt.reason or "")
