"""Unit tests for the :class:`LLMRuntime` ABC contract."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from selffork_orchestrator.runtime.base import ChatMessage, LLMRuntime
from selffork_shared.errors import RuntimeStartError


class _FakeRuntime(LLMRuntime):
    """In-memory fake — never spawns a real process."""

    def __init__(self, model: str = "fake-model", port: int = 12345) -> None:
        self._model = model
        self._port = port
        self._started = False

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        if not self._started:
            raise RuntimeStartError("not started")
        return f"http://127.0.0.1:{self._port}/v1"

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False

    async def health(self) -> bool:
        return self._started

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        if not self._started:
            raise RuntimeStartError("chat called before start")
        return f"fake-reply-to-{len(messages)}-messages"


def test_cannot_instantiate_abstract() -> None:
    with pytest.raises(TypeError):
        LLMRuntime()  # type: ignore[abstract, call-arg]


@pytest.mark.asyncio
async def test_fake_lifecycle() -> None:
    rt = _FakeRuntime()
    assert await rt.health() is False
    await rt.start()
    assert await rt.health() is True
    assert rt.base_url == "http://127.0.0.1:12345/v1"
    await rt.stop()
    assert await rt.health() is False


@pytest.mark.asyncio
async def test_base_url_before_start_raises() -> None:
    rt = _FakeRuntime()
    with pytest.raises(RuntimeStartError):
        _ = rt.base_url


@pytest.mark.asyncio
async def test_start_stop_idempotent() -> None:
    rt = _FakeRuntime()
    await rt.start()
    await rt.start()  # should be safe (fake just re-flags True)
    await rt.stop()
    await rt.stop()
    assert await rt.health() is False
