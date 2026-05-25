"""Unit tests for :class:`MlxServerRuntime` that don't require real mlx-lm.

Real-runtime integration tests live under
``tests/e2e/`` and are gated by ``@pytest.mark.real_runtime``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from selffork_orchestrator.runtime.mlx_server import MlxServerRuntime
from selffork_orchestrator.runtime.sse import StreamDone, TokenChunk
from selffork_shared.config import RuntimeConfig
from selffork_shared.errors import (
    RuntimeMisconfiguredError,
    RuntimeStartError,
    RuntimeUnhealthyError,
    SpeakerStalledError,
)


def test_init_validates_backend() -> None:
    cfg = RuntimeConfig(backend="ollama")
    with pytest.raises(ValueError, match="mlx-server"):
        MlxServerRuntime(cfg)


def test_model_id_available_pre_start() -> None:
    cfg = RuntimeConfig()
    rt = MlxServerRuntime(cfg)
    assert rt.model_id == cfg.model_id


def test_base_url_before_start_raises() -> None:
    cfg = RuntimeConfig()
    rt = MlxServerRuntime(cfg)
    with pytest.raises(RuntimeStartError, match="before start"):
        _ = rt.base_url


@pytest.mark.asyncio
async def test_health_before_start_returns_false() -> None:
    cfg = RuntimeConfig()
    rt = MlxServerRuntime(cfg)
    assert await rt.health() is False


@pytest.mark.asyncio
async def test_stop_before_start_is_noop() -> None:
    cfg = RuntimeConfig()
    rt = MlxServerRuntime(cfg)
    # Should not raise.
    await rt.stop()
    assert await rt.health() is False


# ── Shared-mode unit tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shared_mode_rejects_auto_allocate_port() -> None:
    # Shared mode means we attach to a server someone else started — we
    # MUST know the port. port=0 (auto-allocate) only makes sense when
    # we're spawning the server ourselves.
    cfg = RuntimeConfig(mode="shared", port=0)
    rt = MlxServerRuntime(cfg)
    with pytest.raises(RuntimeStartError, match="requires a concrete port"):
        await rt.start()


@pytest.mark.asyncio
async def test_shared_mode_stop_skips_process_teardown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # In shared mode the runtime never owns a subprocess; stop() must
    # NEVER reach _terminate_group regardless of internal state. Spy on
    # the group-killer to assert it stays untouched.
    cfg = RuntimeConfig(mode="shared", port=8080)
    rt = MlxServerRuntime(cfg)

    calls: list[object] = []

    async def _spy(proc: object) -> None:
        calls.append(proc)

    monkeypatch.setattr(MlxServerRuntime, "_terminate_group", staticmethod(_spy))
    await rt.stop()
    assert calls == []
    assert await rt.health() is False


# ── S-Stream (ADR-011) — streaming chat + warmup wrong-runtime probe ──────────


def _sse_frame(content: str = "", *, finish_reason: str | None = None) -> bytes:
    delta: dict[str, str] = {"content": content} if content else {}
    payload = json.dumps(
        {"choices": [{"delta": delta, "finish_reason": finish_reason}]}
    )
    return f"data: {payload}\n\n".encode()


_SSE_DONE = b"data: [DONE]\n\n"


class _AsyncIterableStream(httpx.AsyncByteStream):
    """SSE byte stream driven by a caller-supplied async-gen factory."""

    def __init__(self, factory: Callable[[], AsyncIterator[bytes]]) -> None:
        self._factory = factory

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._factory():
            yield chunk

    async def aclose(self) -> None:
        return None


def _streaming_runtime(
    factory: Callable[[], AsyncIterator[bytes]],
    *,
    status: int = 200,
) -> MlxServerRuntime:
    """An MlxServerRuntime wired to a MockTransport SSE stream.

    ``_actual_port`` is set directly so chat_stream works without spawning
    a real ``mlx_vlm.server`` (lifecycle is covered by the tests above).
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers={"content-type": "text/event-stream"},
            stream=_AsyncIterableStream(factory),
        )

    cfg = RuntimeConfig(backend="mlx-server", host="127.0.0.1", port=8080)
    rt = MlxServerRuntime(cfg, transport=httpx.MockTransport(handler))
    rt._actual_port = 8080
    return rt


def _hello_stream() -> AsyncIterator[bytes]:
    async def gen() -> AsyncIterator[bytes]:
        yield _sse_frame("hello")
        yield _sse_frame(" world")
        yield _sse_frame("", finish_reason="stop")
        yield _SSE_DONE

    return gen()


@pytest.mark.asyncio
async def test_chat_stream_yields_tokens_then_done() -> None:
    rt = _streaming_runtime(_hello_stream)
    events = [
        ev
        async for ev in rt.chat_stream([{"role": "user", "content": "hi"}])
    ]
    tokens = [e for e in events if isinstance(e, TokenChunk)]
    done = [e for e in events if isinstance(e, StreamDone)]
    assert [t.text for t in tokens] == ["hello", " world"]
    assert len(done) == 1
    assert done[0].full_reply == "hello world"
    assert done[0].finish_reason == "stop"


@pytest.mark.asyncio
async def test_chat_aggregates_stream() -> None:
    rt = _streaming_runtime(_hello_stream)
    out = await rt.chat([{"role": "user", "content": "hi"}])
    assert out == "hello world"


@pytest.mark.asyncio
async def test_chat_stream_marks_stream_true() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_AsyncIterableStream(_hello_stream),
        )

    cfg = RuntimeConfig(backend="mlx-server", host="127.0.0.1", port=8080)
    rt = MlxServerRuntime(cfg, transport=httpx.MockTransport(handler))
    rt._actual_port = 8080
    async for _ in rt.chat_stream([{"role": "user", "content": "hi"}]):
        pass
    assert seen["stream"] is True


@pytest.mark.asyncio
async def test_chat_stream_before_start_raises() -> None:
    cfg = RuntimeConfig(backend="mlx-server")
    rt = MlxServerRuntime(cfg)
    with pytest.raises(RuntimeStartError, match="before start"):
        async for _ in rt.chat_stream([{"role": "user", "content": "x"}]):
            pass


@pytest.mark.asyncio
async def test_chat_stream_non_200_raises_unhealthy() -> None:
    rt = _streaming_runtime(_hello_stream, status=503)
    with pytest.raises(RuntimeUnhealthyError, match="503"):
        async for _ in rt.chat_stream([{"role": "user", "content": "x"}]):
            pass


@pytest.mark.asyncio
async def test_chat_stream_idle_watchdog_raises_stalled() -> None:
    def gen() -> AsyncIterator[bytes]:
        async def inner() -> AsyncIterator[bytes]:
            yield _sse_frame("first")
            await asyncio.sleep(5.0)  # exceeds the watchdog
            yield _sse_frame("never")

        return inner()

    rt = _streaming_runtime(gen)
    with pytest.raises(SpeakerStalledError):
        async for _ in rt.chat_stream(
            [{"role": "user", "content": "x"}], stall_seconds=0.2
        ):
            pass


# ── warmup_probe (wrong-runtime detection) ────────────────────────────────────


@pytest.mark.asyncio
async def test_warmup_probe_passes_when_token_flows() -> None:
    rt = _streaming_runtime(_hello_stream)
    # Must NOT raise — a real mlx_vlm.server emits tokens.
    await rt.warmup_probe(stall_seconds=1.0)


@pytest.mark.asyncio
async def test_warmup_probe_raises_misconfigured_when_stalled() -> None:
    def gen() -> AsyncIterator[bytes]:
        async def inner() -> AsyncIterator[bytes]:
            # No token ever (mlx_lm-on-VLM silent hang signature).
            await asyncio.sleep(5.0)
            yield _sse_frame("never")

        return inner()

    rt = _streaming_runtime(gen)
    with pytest.raises(RuntimeMisconfiguredError, match=r"mlx_vlm\.server"):
        await rt.warmup_probe(stall_seconds=0.2)


@pytest.mark.asyncio
async def test_warmup_probe_raises_misconfigured_on_empty_stream() -> None:
    def gen() -> AsyncIterator[bytes]:
        async def inner() -> AsyncIterator[bytes]:
            # Closes immediately with no content frame.
            yield _SSE_DONE

        return inner()

    rt = _streaming_runtime(gen)
    with pytest.raises(RuntimeMisconfiguredError, match="empty stream"):
        await rt.warmup_probe(stall_seconds=1.0)


@pytest.mark.asyncio
async def test_maybe_warmup_probe_skips_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SELFFORK_MLX_WARMUP", raising=False)

    def gen() -> AsyncIterator[bytes]:
        async def inner() -> AsyncIterator[bytes]:
            # Would stall forever — but the probe must be skipped, so this
            # is never consumed (no hang, no error).
            await asyncio.sleep(30.0)
            yield _sse_frame("never")

        return inner()

    rt = _streaming_runtime(gen)
    # Opt-in env unset ⇒ _maybe_warmup_probe is a no-op (returns fast).
    await asyncio.wait_for(rt._maybe_warmup_probe(), timeout=1.0)


@pytest.mark.asyncio
async def test_maybe_warmup_probe_runs_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SELFFORK_MLX_WARMUP", "true")
    rt = _streaming_runtime(_hello_stream)
    # Spy on warmup_probe so the env-gate is tested without depending on
    # stall timing (the real warmup budget is large by design).
    called: list[bool] = []

    async def _fake_probe(*, stall_seconds: float = 0.0) -> None:
        called.append(True)
        raise RuntimeMisconfiguredError("wrong runtime (test)")

    monkeypatch.setattr(rt, "warmup_probe", _fake_probe)
    with pytest.raises(RuntimeMisconfiguredError):
        await rt._maybe_warmup_probe()
    assert called == [True]
