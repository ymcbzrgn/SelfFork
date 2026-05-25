"""MlxServerRuntime — MVP runtime backed by ``mlx_vlm.server``.

Spawns ``python -m mlx_vlm.server --model <id> --host <host> --port <port>``
in a new process group. Polls ``GET <base>/health`` until ``200 OK`` or
the configured timeout. :meth:`stop` does SIGTERM → grace → SIGKILL on
the whole group. :meth:`chat` POSTs to ``/v1/chat/completions``.

**Why mlx-vlm and not mlx-lm**: Gemma 4 E2B-it is a multimodal model
(text + vision); its PLE-safe 4-bit MLX variant is documented to run on
``mlx_vlm.server`` and verified to load + serve OpenAI-compat chat. The
text-only ``mlx_lm.server`` path emits unmatched-weights warnings and
hangs on inference. ``mlx_vlm`` is a strict superset for our purposes
(text-only chat works fine, vision is unlocked for M5 Body pillar).

The user installs ``mlx-vlm`` themselves (``uv pip install mlx-vlm``) —
deployment-time dep. Default model: **Gemma 4 E2B-it** PLE-safe 4bit
(``FakeRockert543/gemma-4-e2b-it-MLX-4bit``, ~7.1 GB on disk, ~7.6 GB
peak VRAM at moderate context, 128k max context).

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.1, §13;
``project_selffork_jr_is_user_simulator.md``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from collections.abc import AsyncIterator, Sequence

import httpx

from selffork_orchestrator.runtime.base import ChatMessage, LLMRuntime
from selffork_orchestrator.runtime.sse import (
    StreamDone,
    StreamEvent,
    TokenChunk,
    stream_openai_sse,
)
from selffork_shared.config import RuntimeConfig
from selffork_shared.errors import (
    RuntimeMisconfiguredError,
    RuntimeStartError,
    RuntimeUnhealthyError,
    SpeakerStalledError,
)
from selffork_shared.logging import get_logger
from selffork_shared.ports import find_free_port

__all__ = ["MlxServerRuntime"]

_log = get_logger(__name__)

# Grace window after SIGTERM before we escalate to SIGKILL.
_KILL_GRACE_SECONDS = 5.0
# Health-poll backoff: starts cheap, doubles up to a cap.
_POLL_INITIAL_SECONDS = 0.5
_POLL_MAX_SECONDS = 4.0
# ADR-011 §3.3 split timeout for streaming chat — short connect (a dead
# endpoint fails fast) + unbounded read (per-token liveness is enforced
# by the idle-token watchdog, not a wall-clock cap, so a valid hours-long
# CPU generation is never killed mid-flight).
_CONNECT_SECONDS = 5.0
# ADR-011 §3.3 default idle-token watchdog for the round-loop. Generous —
# the FIRST chat after spin-up is the slowest (Metal-kernel compile +
# model warm), and the operator's target is CPU where steady-state tokens
# can be seconds apart. ``None`` would disable the watchdog (allowed but
# not the default — a wedged model must still surface eventually).
_DEFAULT_CHAT_STALL_SECONDS: float | None = 300.0
# ADR-011 §3.5 warmup wrong-runtime probe budget. If a freshly-attached
# server (shared mode) produces NO token within this window, we classify
# it as the ``mlx_lm``-on-VLM hang class and raise
# :class:`RuntimeMisconfiguredError` instead of letting the first real
# chat hang. Generous for a CPU cold-start; tunable via env.
_WARMUP_STALL_SECONDS = 180.0
_ENV_WARMUP = "SELFFORK_MLX_WARMUP"


class MlxServerRuntime(LLMRuntime):
    """LLM runtime backed by ``mlx-lm`` 's OpenAI-compatible HTTP server."""

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if config.backend != "mlx-server":
            raise ValueError(
                f"MlxServerRuntime requires backend='mlx-server', got {config.backend!r}",
            )
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._actual_port: int | None = None
        # Test seam (``httpx.MockTransport``); production leaves it None.
        self._transport = transport

    @property
    def model_id(self) -> str:
        return self._config.model_id

    @property
    def actual_port(self) -> int | None:
        """Port the runtime is bound to, or None if not started yet.

        Useful for parents (``selffork run-many``) that spawn this in
        owned mode and need to tell children which port to attach in
        shared mode — especially when ``config.port == 0`` triggered an
        auto-allocation that the children couldn't have predicted.
        """
        return self._actual_port

    @property
    def base_url(self) -> str:
        if self._actual_port is None:
            raise RuntimeStartError("base_url accessed before start() / after stop()")
        return f"http://{self._config.host}:{self._actual_port}/v1"

    @property
    def _health_url(self) -> str:
        if self._actual_port is None:
            raise RuntimeStartError("health url accessed before start()")
        return f"http://{self._config.host}:{self._actual_port}/health"

    async def start(self) -> None:
        if self._actual_port is not None:
            return
        # Shared mode: parent process owns the server. We only verify it's
        # reachable, never spawn or teardown. Used by ``selffork run-many``
        # so N parallel sessions can hit one warm MLX server.
        if self._config.mode == "shared":
            if self._config.port == 0:
                raise RuntimeStartError(
                    "shared runtime mode requires a concrete port "
                    "(port=0 / auto-allocate is owned-mode only)",
                )
            self._actual_port = self._config.port
            _log.info(
                "runtime_attach_shared",
                backend="mlx-server",
                model=self._config.model_id,
                host=self._config.host,
                port=self._actual_port,
            )
            try:
                await self._wait_ready()
                await self._maybe_warmup_probe()
            except BaseException:
                self._actual_port = None
                raise
            return
        if self._process is not None:
            return
        port = self._config.port if self._config.port != 0 else find_free_port(self._config.host)
        cmd = [
            sys.executable,
            "-m",
            "mlx_vlm.server",
            "--model",
            self._config.model_id,
            "--host",
            self._config.host,
            "--port",
            str(port),
        ]
        _log.info(
            "runtime_start",
            backend="mlx-server",
            model=self._config.model_id,
            host=self._config.host,
            port=port,
            command=cmd,
        )
        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except (OSError, FileNotFoundError) as exc:
            raise RuntimeStartError(
                f"failed to spawn mlx-server (cmd={cmd}): {exc}",
            ) from exc

        self._actual_port = port

        try:
            await self._wait_ready()
            await self._maybe_warmup_probe()
        except BaseException:
            await self.stop()
            raise

    async def _wait_ready(self) -> None:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self._config.startup_timeout_seconds
        delay = _POLL_INITIAL_SECONDS
        last_error: str = "unknown"

        while True:
            self._raise_if_exited_early()

            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(self._health_url)
                if resp.status_code == 200:
                    _log.info("runtime_ready", port=self._actual_port)
                    return
                last_error = f"HTTP {resp.status_code}"
            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"

            now = loop.time()
            if now >= deadline:
                raise RuntimeStartError(
                    f"mlx-server did not become healthy within "
                    f"{self._config.startup_timeout_seconds}s "
                    f"(last error: {last_error})",
                )
            await asyncio.sleep(min(delay, deadline - now))
            delay = min(delay * 2, _POLL_MAX_SECONDS)

    def _raise_if_exited_early(self) -> None:
        proc = self._process
        if proc is None or proc.returncode is None:
            return
        stderr_preview = ""
        if proc.stderr is not None:
            try:
                buf = proc.stderr._buffer  # type: ignore[attr-defined]
                stderr_preview = bytes(buf).decode("utf-8", errors="replace")[:500]
            except (AttributeError, Exception):
                stderr_preview = "<stderr unavailable>"
        raise RuntimeStartError(
            f"mlx-server exited prematurely with code {proc.returncode}: {stderr_preview}",
        )

    async def stop(self) -> None:
        # Shared mode: parent owns the server lifecycle, we just detach.
        if self._config.mode == "shared":
            if self._actual_port is not None:
                _log.info("runtime_detach_shared", port=self._actual_port)
            self._actual_port = None
            return
        proc = self._process
        if proc is None:
            return
        if proc.returncode is None:
            await self._terminate_group(proc)
        _log.info("runtime_stopped", exit_code=proc.returncode)
        self._process = None
        self._actual_port = None

    @staticmethod
    async def _terminate_group(proc: asyncio.subprocess.Process) -> None:
        with contextlib.suppress(ProcessLookupError, OSError):
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=_KILL_GRACE_SECONDS)
        except TimeoutError:
            _log.warning("runtime_kill_after_timeout", grace_s=_KILL_GRACE_SECONDS)
            with contextlib.suppress(ProcessLookupError, OSError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except TimeoutError:
                _log.error("runtime_did_not_die_after_kill")

    async def health(self) -> bool:
        if self._actual_port is None:
            return False
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(self._health_url)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False
        return resp.status_code == 200

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Run one chat turn; return the assistant text (ADR-011 aggregator).

        Drains :meth:`chat_stream` so the streaming wire protocol + the
        idle-token watchdog are the single source of truth. The round-loop
        keeps calling this non-streaming surface; the watchdog means a
        wedged model now raises :class:`SpeakerStalledError` instead of
        hanging the round forever.
        """
        chunks: list[str] = []
        full: str | None = None
        async for event in self.chat_stream(
            messages, max_tokens=max_tokens, temperature=temperature
        ):
            if isinstance(event, TokenChunk):
                chunks.append(event.text)
                continue
            full = event.full_reply
        return full if full is not None else "".join(chunks)

    async def chat_stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        stall_seconds: float | None = _DEFAULT_CHAT_STALL_SECONDS,
    ) -> AsyncIterator[StreamEvent]:
        """Stream one chat turn token-by-token (ADR-011 §3.1/§3.3).

        Yields :class:`TokenChunk` per SSE frame, finalised by one
        :class:`StreamDone`. ``stall_seconds`` is the idle-token watchdog
        (``None`` disables it). Shares the SSE consume loop with the Talk
        Speaker via :mod:`selffork_orchestrator.runtime.sse`.

        Raises:
            RuntimeStartError: called before start() / after stop().
            RuntimeUnhealthyError: connect error / non-200 / malformed SSE.
            SpeakerStalledError: no token within ``stall_seconds``.
        """
        if self._actual_port is None:
            raise RuntimeStartError("chat() called before start() / after stop()")
        body: dict[str, object] = {
            "model": self._config.model_id,
            "messages": list(messages),
            "stream": True,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature

        url = f"{self.base_url}/chat/completions"
        timeout = httpx.Timeout(
            connect=_CONNECT_SECONDS,
            read=None,
            write=_CONNECT_SECONDS,
            pool=_CONNECT_SECONDS,
        )
        try:
            async with httpx.AsyncClient(
                timeout=timeout, transport=self._transport
            ) as client, client.stream("POST", url, json=body) as resp:
                if resp.status_code != 200:
                    body_bytes = await resp.aread()
                    raise RuntimeUnhealthyError(
                        f"chat HTTP {resp.status_code}: "
                        f"{body_bytes.decode('utf-8', errors='replace')[:500]}"
                    )
                async for event in stream_openai_sse(
                    resp, stall_seconds=stall_seconds
                ):
                    yield event
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
            raise RuntimeUnhealthyError(
                f"chat request failed: {type(exc).__name__}: {exc}",
            ) from exc

    async def warmup_probe(
        self, *, stall_seconds: float = _WARMUP_STALL_SECONDS
    ) -> None:
        """Detect the ``mlx_lm``-on-VLM silent-hang class at spin-up.

        Runs a tiny generation; if NO token arrives within
        ``stall_seconds`` the server is the wrong runtime for the Gemma 4
        VLM (it loads weights but never emits tokens — documented at the
        top of this module) and we raise
        :class:`RuntimeMisconfiguredError` with the canonical-spawn fix,
        instead of letting the first real chat hang indefinitely.

        A correct ``mlx_vlm.server`` emits tokens even on a slow CPU
        (trickle), so the probe passes on the first token.
        """
        try:
            async for event in self.chat_stream(
                # A small-but-not-1 cap: Gemma 4 E2B spends tokens on a
                # reasoning pass before visible content, so ``max_tokens=1``
                # can come back empty on a *correct* runtime and trip a
                # false ``RuntimeMisconfiguredError`` (audit-god S-Stream
                # backend finding #2). 16 is enough to see a real token
                # trickle without a meaningful warmup cost.
                [{"role": "user", "content": "ok"}],
                max_tokens=16,
                stall_seconds=stall_seconds,
            ):
                if isinstance(event, TokenChunk) and event.text:
                    return  # produced a token → correct runtime
                if isinstance(event, StreamDone):
                    if event.full_reply:
                        return
                    break
        except SpeakerStalledError as exc:
            raise RuntimeMisconfiguredError(
                "model produced no token within "
                f"{stall_seconds}s warmup — the endpoint is likely the "
                "wrong runtime for the Gemma 4 VLM (text-only mlx_lm.server "
                "loads weights but hangs on inference). Canonical spawn: "
                "`python -m mlx_vlm.server --model <id> --host <h> --port <p>`."
            ) from exc
        # Stream ended with no content at all — also a misconfiguration
        # signal (a healthy VLM returns at least one token for "ok").
        raise RuntimeMisconfiguredError(
            "warmup produced an empty stream — endpoint may be the wrong "
            "runtime for the Gemma 4 VLM (use `python -m mlx_vlm.server`)."
        )

    async def _maybe_warmup_probe(self) -> None:
        """Run :meth:`warmup_probe` when opted in via ``SELFFORK_MLX_WARMUP``.

        Default OFF: the always-on idle-token watchdog in
        :meth:`chat_stream` already converts a wedged model into a bounded
        :class:`SpeakerStalledError` on the first real chat, so warmup is
        an *early-detection* convenience (fail at spin-up vs first chat),
        not the primary no-hang guarantee. It adds a one-token generation
        to startup, so it stays opt-in for the spawn path (which already
        launches the correct ``mlx_vlm.server``); deployments that attach
        to an external endpoint can enable it to fail fast.
        """
        raw = os.environ.get(_ENV_WARMUP, "").strip().lower()
        if raw not in {"true", "1", "yes"}:
            return
        # Raises RuntimeMisconfiguredError on a wedged/wrong runtime; the
        # caller (start) is inside a try that tears down per mode.
        await self.warmup_probe()
