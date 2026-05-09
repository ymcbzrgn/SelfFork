"""Tests for :class:`TelegramBridge` ABC + :class:`NullTelegramBridge`."""
from __future__ import annotations

import pytest

from selffork_orchestrator.telegram.bridge import (
    NullTelegramBridge,
    TelegramMessage,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_null_bridge_returns_undelivered() -> None:
    bridge = NullTelegramBridge()
    attempt = await bridge.notify(
        TelegramMessage(
            level="info",
            text="hello",
            session_id="session-1",
        ),
    )
    assert attempt.delivered is False
    assert attempt.reason is not None
    assert "NullTelegramBridge" in attempt.reason
    assert attempt.sent_at is not None


@pytest.mark.anyio
async def test_null_bridge_handles_all_levels() -> None:
    bridge = NullTelegramBridge()
    for level in ("info", "warn", "crit"):
        attempt = await bridge.notify(
            TelegramMessage(level=level, text="x", session_id="x"),  # type: ignore[arg-type]
        )
        assert attempt.delivered is False


@pytest.mark.anyio
async def test_null_bridge_records_chat_id_none() -> None:
    bridge = NullTelegramBridge()
    attempt = await bridge.notify(
        TelegramMessage(level="info", text="hi", session_id="s"),
    )
    assert attempt.chat_id is None
