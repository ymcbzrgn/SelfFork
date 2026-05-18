"""Unit tests for :mod:`selffork_orchestrator.talk.speaker` — S1 Talk Loop.

The Speaker client is exercised against an ``httpx.MockTransport`` — real
httpx, a stub transport — so there is no network and no model process.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from selffork_orchestrator.talk.speaker import SpeakerClient
from selffork_shared.errors import RuntimeUnhealthyError


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> SpeakerClient:
    return SpeakerClient(
        base_url="http://stub:8080/v1",
        model="gemma-4-e2b",
        transport=httpx.MockTransport(handler),
    )


def _ok(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
        },
    )


class TestReply:
    @pytest.mark.anyio
    async def test_returns_assistant_content(self) -> None:
        speaker = _client(lambda _req: _ok("hello from Self Jr"))
        out = await speaker.reply([{"role": "user", "content": "hi"}])
        assert out == "hello from Self Jr"

    @pytest.mark.anyio
    async def test_posts_model_and_messages(self) -> None:
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return _ok("ok")

        speaker = _client(handler)
        await speaker.reply([{"role": "user", "content": "ping"}])
        assert seen["model"] == "gemma-4-e2b"
        assert seen["messages"] == [{"role": "user", "content": "ping"}]
        assert seen["stream"] is False

    @pytest.mark.anyio
    async def test_targets_chat_completions_endpoint(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return _ok("ok")

        speaker = _client(handler)
        await speaker.reply([{"role": "user", "content": "x"}])
        assert seen["url"] == "http://stub:8080/v1/chat/completions"

    @pytest.mark.anyio
    async def test_connect_error_raises_unhealthy(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        speaker = _client(handler)
        with pytest.raises(RuntimeUnhealthyError):
            await speaker.reply([{"role": "user", "content": "x"}])

    @pytest.mark.anyio
    async def test_non_200_raises_unhealthy(self) -> None:
        speaker = _client(lambda _req: httpx.Response(500, text="boom"))
        with pytest.raises(RuntimeUnhealthyError):
            await speaker.reply([{"role": "user", "content": "x"}])

    @pytest.mark.anyio
    async def test_malformed_body_raises_unhealthy(self) -> None:
        speaker = _client(lambda _req: httpx.Response(200, json={"nope": 1}))
        with pytest.raises(RuntimeUnhealthyError):
            await speaker.reply([{"role": "user", "content": "x"}])

    @pytest.mark.anyio
    async def test_non_string_content_raises_unhealthy(self) -> None:
        speaker = _client(
            lambda _req: httpx.Response(
                200,
                json={"choices": [{"message": {"content": 123}}]},
            ),
        )
        with pytest.raises(RuntimeUnhealthyError):
            await speaker.reply([{"role": "user", "content": "x"}])
