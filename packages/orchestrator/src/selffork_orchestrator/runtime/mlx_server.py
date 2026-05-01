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
from collections.abc import Sequence

import httpx

from selffork_orchestrator.runtime.base import ChatMessage, LLMRuntime
from selffork_shared.config import RuntimeConfig
from selffork_shared.errors import RuntimeStartError, RuntimeUnhealthyError
from selffork_shared.logging import get_logger
from selffork_shared.ports import find_free_port

__all__ = ["MlxServerRuntime"]

_log = get_logger(__name__)

# Grace window after SIGTERM before we escalate to SIGKILL.
_KILL_GRACE_SECONDS = 5.0
# Health-poll backoff: starts cheap, doubles up to a cap.
_POLL_INITIAL_SECONDS = 0.5
_POLL_MAX_SECONDS = 4.0
# Default chat-completion timeout. The FIRST chat after runtime spin-up
# is the slowest — mlx-lm compiles Metal kernels and warms the model on
# the first inference. Subsequent calls are fast. 300s gives Gemma 4 E2B
# 4bit on Apple Silicon plenty of headroom for the cold call; steady-
# state per-round latency is 5-30s.
_CHAT_TIMEOUT_SECONDS = 300.0


class MlxServerRuntime(LLMRuntime):
    """LLM runtime backed by ``mlx-lm`` 's OpenAI-compatible HTTP server."""

    def __init__(self, config: RuntimeConfig) -> None:
        if config.backend != "mlx-server":
            raise ValueError(
                f"MlxServerRuntime requires backend='mlx-server', got {config.backend!r}",
            )
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._actual_port: int | None = None

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
        if self._actual_port is None:
            raise RuntimeStartError("chat() called before start() / after stop()")

        body: dict[str, object] = {
            "model": self._config.model_id,
            "messages": list(messages),
            "stream": False,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature

        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, json=body)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
            raise RuntimeUnhealthyError(
                f"chat request failed: {type(exc).__name__}: {exc}",
            ) from exc

        if resp.status_code != 200:
            raise RuntimeUnhealthyError(
                f"chat HTTP {resp.status_code}: {resp.text[:500]}",
            )

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeUnhealthyError(
                f"chat response malformed: {type(exc).__name__}: {exc}; body={resp.text[:500]}",
            ) from exc

        if not isinstance(content, str):
            raise RuntimeUnhealthyError(
                f"chat response content is not a string (got {type(content).__name__})",
            )
        return content
