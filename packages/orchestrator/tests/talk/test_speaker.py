"""Unit tests for :mod:`selffork_orchestrator.talk.speaker` — S1 + S-Stream.

The Speaker client is exercised against an ``httpx.MockTransport`` — real
httpx, a stub transport — so there is no network and no model process.

Coverage:

* **Reply (back-compat)** — the legacy non-streaming surface still works
  via the streaming path under the hood; existing call-sites are
  unchanged.
* **Reply-stream (ADR-011)** — token chunks arrive as they are produced;
  the stream finalises with a single :class:`StreamDone`; the idle-token
  watchdog distinguishes "wedged" from "slow but alive"; cancellation
  propagates without hanging; transport errors surface as
  :class:`RuntimeUnhealthyError`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest

from selffork_orchestrator.talk.speaker import (
    SpeakerClient,
    StreamDone,
    TokenChunk,
)
from selffork_shared.errors import RuntimeUnhealthyError, SpeakerStalledError

# ── SSE wire helpers (tests only) ───────────────────────────────────────


def _sse_frame(content: str = "", *, finish_reason: str | None = None) -> bytes:
    """Encode one OpenAI streaming SSE frame.

    ``content`` empty + ``finish_reason="stop"`` produces a closer frame
    (no delta.content, just the finish marker).
    """
    delta: dict[str, str] = {"content": content} if content else {}
    payload = json.dumps({"choices": [{"delta": delta, "finish_reason": finish_reason}]})
    return f"data: {payload}\n\n".encode()


_SSE_DONE = b"data: [DONE]\n\n"


class _AsyncIterableStream(httpx.AsyncByteStream):
    """An ``httpx.AsyncByteStream`` driven by a caller-supplied async gen.

    Each call to ``__aiter__`` invokes ``factory`` fresh, so a single
    stream object can be re-iterated (httpx may do so internally) and
    the test author controls inter-chunk timing via ``asyncio.sleep``
    inside the generator.
    """

    def __init__(
        self,
        factory: Callable[[], AsyncIterator[bytes]],
    ) -> None:
        self._factory = factory

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._factory():
            yield chunk

    async def aclose(self) -> None:
        return None


def _stream_response(
    factory: Callable[[], AsyncIterator[bytes]],
    *,
    status: int = 200,
) -> Callable[[httpx.Request], httpx.Response]:
    """Build a MockTransport handler that returns an SSE streamed response."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers={"content-type": "text/event-stream"},
            stream=_AsyncIterableStream(factory),
        )

    return handler


def _stream_client(
    handler: Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]],
    *,
    default_stall: float | None = None,
) -> SpeakerClient:
    """Speaker bound to an ``httpx.MockTransport`` for streaming tests.

    ``default_stall=None`` disables the per-call watchdog default so a
    test that doesn't care about watchdog timing isn't surprised by the
    production default firing during a slow async-step.
    """
    return SpeakerClient(
        base_url="http://stub:8080/v1",
        model="gemma-4-e2b",
        default_stall_seconds=default_stall,
        transport=httpx.MockTransport(handler),
    )


# ── Back-compat: the legacy non-streaming reply() surface ───────────────


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> SpeakerClient:
    return SpeakerClient(
        base_url="http://stub:8080/v1",
        model="gemma-4-e2b",
        default_stall_seconds=None,
        transport=httpx.MockTransport(handler),
    )


def _hello_world_stream() -> AsyncIterator[bytes]:
    async def gen() -> AsyncIterator[bytes]:
        yield _sse_frame("hello from")
        yield _sse_frame(" Self Jr")
        yield _sse_frame("", finish_reason="stop")
        yield _SSE_DONE

    return gen()


class TestReply:
    """The legacy non-streaming :meth:`SpeakerClient.reply` surface.

    ``reply()`` is now a thin aggregator over :meth:`reply_stream` — its
    public contract (returns the full text) is unchanged but the wire
    body now requests ``stream: true`` because draining a stream is the
    only path that survives an hours-long CPU generation (ADR-011 §3).
    """

    @pytest.mark.anyio
    async def test_returns_assistant_content(self) -> None:
        speaker = _client(_stream_response(_hello_world_stream))
        out = await speaker.reply([{"role": "user", "content": "hi"}])
        assert out == "hello from Self Jr"

    @pytest.mark.anyio
    async def test_posts_model_and_messages_streaming(self) -> None:
        """The wire body always opts in to streaming under ADR-011."""
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_AsyncIterableStream(_hello_world_stream),
            )

        speaker = _client(handler)
        await speaker.reply([{"role": "user", "content": "ping"}])
        assert seen["model"] == "gemma-4-e2b"
        assert seen["messages"] == [{"role": "user", "content": "ping"}]
        assert seen["stream"] is True

    @pytest.mark.anyio
    async def test_targets_chat_completions_endpoint(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_AsyncIterableStream(_hello_world_stream),
            )

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
        with pytest.raises(RuntimeUnhealthyError) as info:
            await speaker.reply([{"role": "user", "content": "x"}])
        assert "boom" in str(info.value)

    @pytest.mark.anyio
    async def test_malformed_sse_frame_raises_unhealthy(self) -> None:
        """A ``data:`` line with invalid JSON breaks the wire protocol."""

        def gen() -> AsyncIterator[bytes]:
            async def inner() -> AsyncIterator[bytes]:
                yield b"data: {not-json\n\n"

            return inner()

        speaker = _client(_stream_response(gen))
        with pytest.raises(RuntimeUnhealthyError) as info:
            await speaker.reply([{"role": "user", "content": "x"}])
        assert "SSE frame malformed" in str(info.value)


# ── Streaming (ADR-011 §3) ──────────────────────────────────────────────


class TestReplyStream:
    @pytest.mark.anyio
    async def test_stream_yields_token_chunks_then_done(self) -> None:
        speaker = _stream_client(_stream_response(_hello_world_stream))
        events: list[object] = []
        async for ev in speaker.reply_stream([{"role": "user", "content": "x"}]):
            events.append(ev)
        token_events = [e for e in events if isinstance(e, TokenChunk)]
        done_events = [e for e in events if isinstance(e, StreamDone)]
        assert [t.text for t in token_events] == ["hello from", " Self Jr"]
        assert len(done_events) == 1
        assert done_events[0].full_reply == "hello from Self Jr"
        assert done_events[0].finish_reason == "stop"

    @pytest.mark.anyio
    async def test_stream_full_reply_concats_chunks(self) -> None:
        """``full_reply`` is the concatenation of every chunk seen."""

        def gen() -> AsyncIterator[bytes]:
            async def inner() -> AsyncIterator[bytes]:
                for word in ["a", "b", "c", "d"]:
                    yield _sse_frame(word)
                yield _sse_frame("", finish_reason="stop")
                yield _SSE_DONE

            return inner()

        speaker = _stream_client(_stream_response(gen))
        chunks: list[str] = []
        full: str | None = None
        async for ev in speaker.reply_stream([{"role": "user", "content": "x"}]):
            if isinstance(ev, TokenChunk):
                chunks.append(ev.text)
            else:
                full = ev.full_reply
        assert chunks == ["a", "b", "c", "d"]
        assert full == "abcd"

    @pytest.mark.anyio
    async def test_stream_request_body_marks_stream_true(self) -> None:
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_AsyncIterableStream(_hello_world_stream),
            )

        speaker = _stream_client(handler)
        async for _ in speaker.reply_stream([{"role": "user", "content": "x"}]):
            pass
        assert seen["stream"] is True

    @pytest.mark.anyio
    async def test_stream_idle_watchdog_raises_stalled(self) -> None:
        """``stall_seconds`` fires when no token arrives in time."""

        def gen() -> AsyncIterator[bytes]:
            async def inner() -> AsyncIterator[bytes]:
                yield _sse_frame("first")
                # Long sleep — longer than the stall watchdog.
                await asyncio.sleep(5.0)
                yield _sse_frame("never reached")

            return inner()

        speaker = _stream_client(_stream_response(gen))
        with pytest.raises(SpeakerStalledError) as info:
            async for _ in speaker.reply_stream(
                [{"role": "user", "content": "x"}],
                stall_seconds=0.2,
            ):
                pass
        assert "wedged" in str(info.value).lower() or "stalled" in str(info.value).lower()

    @pytest.mark.anyio
    async def test_stream_watchdog_disabled_runs_unbounded(self) -> None:
        """``stall_seconds=None`` disables the watchdog (slow stream OK)."""

        def gen() -> AsyncIterator[bytes]:
            async def inner() -> AsyncIterator[bytes]:
                for word in ["s", "l", "o", "w"]:
                    # Slower than what the watchdog would tolerate, but
                    # tolerable under stall_seconds=None.
                    await asyncio.sleep(0.05)
                    yield _sse_frame(word)
                yield _sse_frame("", finish_reason="stop")
                yield _SSE_DONE

            return inner()

        speaker = _stream_client(_stream_response(gen))
        text = ""
        async for ev in speaker.reply_stream(
            [{"role": "user", "content": "x"}],
            stall_seconds=None,
        ):
            if isinstance(ev, TokenChunk):
                text += ev.text
            else:
                text = ev.full_reply
        assert text == "slow"

    @pytest.mark.anyio
    async def test_stream_connect_error_raises_unhealthy(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        speaker = _stream_client(handler)
        with pytest.raises(RuntimeUnhealthyError):
            async for _ in speaker.reply_stream([{"role": "user", "content": "x"}]):
                pass

    @pytest.mark.anyio
    async def test_stream_non_200_raises_unhealthy_with_body(self) -> None:
        speaker = _stream_client(lambda _req: httpx.Response(503, text="model loading"))
        with pytest.raises(RuntimeUnhealthyError) as info:
            async for _ in speaker.reply_stream([{"role": "user", "content": "x"}]):
                pass
        assert "503" in str(info.value)
        assert "model loading" in str(info.value)

    @pytest.mark.anyio
    async def test_stream_ignores_heartbeat_and_blank_lines(self) -> None:
        """SSE heartbeat / blank / ``event:`` lines pass through silently."""

        def gen() -> AsyncIterator[bytes]:
            async def inner() -> AsyncIterator[bytes]:
                yield b": heartbeat comment\n\n"
                yield b"event: ping\n\n"
                yield _sse_frame("hi")
                yield b"\n\n"
                yield _sse_frame("", finish_reason="stop")
                yield _SSE_DONE

            return inner()

        speaker = _stream_client(_stream_response(gen))
        tokens: list[str] = []
        full: str | None = None
        async for ev in speaker.reply_stream([{"role": "user", "content": "x"}]):
            if isinstance(ev, TokenChunk):
                tokens.append(ev.text)
            else:
                full = ev.full_reply
        assert tokens == ["hi"]
        assert full == "hi"

    @pytest.mark.anyio
    async def test_stream_cancellation_propagates_without_hang(self) -> None:
        """Breaking out of the async-for closes the stream cleanly."""

        def gen() -> AsyncIterator[bytes]:
            async def inner() -> AsyncIterator[bytes]:
                counter = 0
                while True:
                    yield _sse_frame(f"t{counter}")
                    await asyncio.sleep(0.01)
                    counter += 1

            return inner()

        speaker = _stream_client(_stream_response(gen))

        seen = 0

        # The whole test must return quickly — bound the iteration by a
        # wall-clock guard so the test author can't trap themselves in
        # an actually-hanging stream.
        async def consume() -> int:
            nonlocal seen
            async for ev in speaker.reply_stream(
                [{"role": "user", "content": "x"}],
                stall_seconds=None,
            ):
                if isinstance(ev, TokenChunk):
                    seen += 1
                    if seen >= 3:
                        break
            return seen

        out = await asyncio.wait_for(consume(), timeout=2.0)
        assert out == 3

    @pytest.mark.anyio
    async def test_stream_done_when_finish_reason_arrives_without_done(
        self,
    ) -> None:
        """A finish_reason="stop" frame closes the stream even without [DONE]."""

        def gen() -> AsyncIterator[bytes]:
            async def inner() -> AsyncIterator[bytes]:
                yield _sse_frame("only token")
                # A real server may close the connection right after the
                # finish_reason frame; the stream surface tolerates both
                # paths (explicit [DONE] or just close).
                yield _sse_frame("", finish_reason="stop")

            return inner()

        speaker = _stream_client(_stream_response(gen))
        chunks: list[str] = []
        full: str | None = None
        finish: str | None = None
        async for ev in speaker.reply_stream([{"role": "user", "content": "x"}]):
            if isinstance(ev, TokenChunk):
                chunks.append(ev.text)
            else:
                full = ev.full_reply
                finish = ev.finish_reason
        # No [DONE] arrived — but the OpenAI finish_reason "stop" frame
        # is sufficient by itself to surface the StreamDone with the
        # finish_reason propagated.
        assert chunks == ["only token"]
        assert full == "only token"
        assert finish == "stop"

    @pytest.mark.anyio
    async def test_stream_default_stall_used_when_param_omitted(self) -> None:
        """The constructor default fires when ``stall_seconds`` is omitted."""

        def gen() -> AsyncIterator[bytes]:
            async def inner() -> AsyncIterator[bytes]:
                yield _sse_frame("hi")
                await asyncio.sleep(5.0)
                yield _sse_frame("never")

            return inner()

        speaker = SpeakerClient(
            base_url="http://stub:8080/v1",
            model="gemma-4-e2b",
            default_stall_seconds=0.2,
            transport=httpx.MockTransport(_stream_response(gen)),
        )
        with pytest.raises(SpeakerStalledError):
            async for _ in speaker.reply_stream([{"role": "user", "content": "x"}]):
                pass
