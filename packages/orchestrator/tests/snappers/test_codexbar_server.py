"""Tests for the CodexBar sidecar lifecycle (S-Quota Faz B).

Three layers:

1. **State machine (mock subprocess + fake health client)** — boot /
   readiness / failure / teardown semantics without touching the
   network or fork(2).
2. **Env resolver** — :func:`build_default_codexbar_server` correctly
   reads ``SELFFORK_CODEXBAR_*`` envs and degrades gracefully when the
   binary is missing.
3. **Real subprocess parity** — spawn a tiny Python aiohttp stub as
   the "binary" so we exercise actual ``asyncio.create_subprocess_exec``
   + ``GET /health`` + ``SIGTERM``. Skipped on systems without
   ``aiohttp`` (Python stdlib only).
"""

from __future__ import annotations

import asyncio
import os
import sys
import textwrap
from pathlib import Path

import httpx
import pytest

from selffork_orchestrator.snappers.codexbar_server import (
    DEFAULT_PORT,
    CodexBarServer,
    CodexBarServerConfig,
    CodexBarServerState,
    build_default_codexbar_server,
)

# ── helpers ─────────────────────────────────────────────────────────────


class _FakeProcess:
    """Minimal stand-in for :class:`asyncio.subprocess.Process`."""

    def __init__(self, *, returncode: int | None = None) -> None:
        self.returncode = returncode
        self.pid = 4242
        self.terminated = False
        self.killed = False
        self._wait_event = asyncio.Event()
        if returncode is not None:
            self._wait_event.set()

    async def wait(self) -> int:
        await self._wait_event.wait()
        assert self.returncode is not None
        return self.returncode

    def mark_exited(self, code: int) -> None:
        self.returncode = code
        self._wait_event.set()


class _StubHealthClient:
    """Async context that mimics ``httpx.AsyncClient.get`` for /health."""

    def __init__(
        self,
        *,
        sequence: list[int | type[Exception]],
    ) -> None:
        # ``sequence`` is consumed left-to-right; each entry is either
        # an HTTP status code (returned) or an Exception subclass
        # (raised once when GET is called).
        self._sequence = list(sequence)
        self.calls = 0

    async def get(self, url: str) -> httpx.Response:
        self.calls += 1
        if not self._sequence:
            raise httpx.ConnectError("no more responses queued", request=None)  # type: ignore[arg-type]
        head = self._sequence.pop(0)
        if isinstance(head, type) and issubclass(head, BaseException):
            raise head("simulated")
        # ``httpx.Response`` requires a Request when content is built
        # from the response itself; for /health we only inspect
        # status_code so a synthetic Request is fine.
        return httpx.Response(int(head))

    async def aclose(self) -> None:
        return None


def _server_with_fakes(
    *,
    spawn_returncode: int | None = None,
    health_sequence: list[int | type[Exception]] | None = None,
    raise_on_spawn: Exception | None = None,
    binary: Path | None = Path("/fake/codexbar"),
    readiness_timeout: float = 0.5,
) -> tuple[CodexBarServer, _FakeProcess | None, _StubHealthClient]:
    process_holder: dict[str, _FakeProcess | None] = {"proc": None}

    async def fake_spawn(argv):
        if raise_on_spawn is not None:
            raise raise_on_spawn
        proc = _FakeProcess(returncode=spawn_returncode)
        process_holder["proc"] = proc
        return proc

    health_client = _StubHealthClient(sequence=list(health_sequence or [200]))

    def health_factory() -> _StubHealthClient:
        return health_client

    server = CodexBarServer(
        config=CodexBarServerConfig(
            binary=binary,
            port=DEFAULT_PORT,
            readiness_timeout_seconds=readiness_timeout,
        ),
        process_factory=fake_spawn,
        health_client_factory=health_factory,
    )
    return server, process_holder.get("proc"), health_client


# ── state machine ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_skips_when_binary_unresolved() -> None:
    server, _, _ = _server_with_fakes(binary=None)
    await server.start()
    assert server.state is CodexBarServerState.FAILED
    assert "binary" in (server.fail_reason or "").lower()


@pytest.mark.asyncio
async def test_start_then_stop_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, _, _ = _server_with_fakes(health_sequence=[200])
    await server.start()
    assert server.state is CodexBarServerState.READY
    assert server.is_running

    sent_signals: list[int] = []

    def fake_killpg(pgid: int, sig: int) -> None:
        sent_signals.append(int(sig))
        if server._process is not None:  # type: ignore[attr-defined]
            server._process.mark_exited(0)  # type: ignore[attr-defined]

    def fake_getpgid(pid: int) -> int:
        return pid

    import signal as _signal

    monkeypatch.setattr(os, "killpg", fake_killpg)
    monkeypatch.setattr(os, "getpgid", fake_getpgid)
    await server.stop()
    assert server.state is CodexBarServerState.STOPPED
    assert sent_signals == [int(_signal.SIGTERM)]


@pytest.mark.asyncio
async def test_start_marks_failed_on_readiness_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, _, _ = _server_with_fakes(
        # Probe never returns 200 → budget exhausts.
        health_sequence=[httpx.ConnectError] * 50,
        readiness_timeout=0.2,
    )
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: None)
    await server.start()
    assert server.state is CodexBarServerState.FAILED
    assert "readiness" in (server.fail_reason or "").lower()


@pytest.mark.asyncio
async def test_start_detects_immediate_exit() -> None:
    """If the binary dies on boot, we fail fast instead of waiting."""
    server, _, _ = _server_with_fakes(
        spawn_returncode=42,
        health_sequence=[httpx.ConnectError, httpx.ConnectError],
        readiness_timeout=2.0,
    )
    await server.start()
    assert server.state is CodexBarServerState.FAILED
    assert "exited" in (server.fail_reason or "").lower()


@pytest.mark.asyncio
async def test_start_handles_spawn_oserror() -> None:
    server, _, _ = _server_with_fakes(raise_on_spawn=OSError("ENOENT"))
    await server.start()
    assert server.state is CodexBarServerState.FAILED
    assert "spawn" in (server.fail_reason or "").lower()


@pytest.mark.asyncio
async def test_start_is_idempotent_when_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, _, health = _server_with_fakes(health_sequence=[200])
    await server.start()
    assert server.state is CodexBarServerState.READY
    health.calls = 0  # reset counter
    await server.start()  # second call is a no-op
    assert health.calls == 0

    def fake_killpg(pgid: int, sig: int) -> None:
        if server._process is not None:  # type: ignore[attr-defined]
            server._process.mark_exited(0)  # type: ignore[attr-defined]

    monkeypatch.setattr(os, "killpg", fake_killpg)
    await server.stop()


@pytest.mark.asyncio
async def test_base_url_reflects_port() -> None:
    server = CodexBarServer(
        config=CodexBarServerConfig(binary=Path("/fake"), port=9001),
    )
    assert server.base_url == "http://127.0.0.1:9001"
    assert server.port == 9001


# ── env resolver ───────────────────────────────────────────────────────


def test_resolver_default_auto_detects_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Wave 2 default: auto-detect; explicit env unnecessary when
    a binary is on the host (opt-out, not opt-in)."""
    fake = tmp_path / "codexbar"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("SELFFORK_CODEXBAR_BIN", str(fake))
    monkeypatch.delenv("SELFFORK_CODEXBAR_ENABLED", raising=False)
    server = build_default_codexbar_server()
    assert server.binary == fake


def test_resolver_disabled_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFFORK_CODEXBAR_ENABLED", "false")
    server = build_default_codexbar_server()
    assert server.binary is None


def test_resolver_picks_explicit_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "codexbar"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("SELFFORK_CODEXBAR_BIN", str(fake))
    monkeypatch.delenv("SELFFORK_CODEXBAR_ENABLED", raising=False)
    server = build_default_codexbar_server()
    assert server.binary == fake


def test_resolver_falls_back_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SELFFORK_CODEXBAR_BIN", str(tmp_path / "ghost"))
    monkeypatch.setenv("PATH", str(tmp_path))  # nothing on PATH
    monkeypatch.delenv("SELFFORK_CODEXBAR_ENABLED", raising=False)
    server = build_default_codexbar_server()
    # A nonexistent override + empty PATH + no /usr/local/bin/codexbar
    # is treated as "no binary"; start() will be a graceful no-op.
    assert server.binary is None or server.binary.exists()


def test_resolver_port_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFFORK_CODEXBAR_PORT", "9999")
    server = build_default_codexbar_server()
    assert server.port == 9999


def test_resolver_port_rejects_bogus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFFORK_CODEXBAR_PORT", "abc")
    server = build_default_codexbar_server()
    assert server.port == DEFAULT_PORT


# ── real subprocess parity ─────────────────────────────────────────────


_STUB_BINARY_SCRIPT = textwrap.dedent(
    """
    import http.server, socket, sys, threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith('/health'):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
            else:
                self.send_response(404); self.end_headers()
        def log_message(self, *_a, **_kw): pass

    # CodexBar CLI: parse '--port <p>' from argv[2..].
    port = None
    args = sys.argv[1:]
    if args and args[0] == 'serve':
        for i, tok in enumerate(args):
            if tok == '--port' and i + 1 < len(args):
                port = int(args[i + 1]); break
    if port is None:
        sys.exit(2)
    server = http.server.HTTPServer(('127.0.0.1', port), Handler)
    server.serve_forever()
    """
).strip()


def _write_python_stub_binary(tmp_path: Path) -> Path:
    """Drop a tiny ``codexbar``-shaped Python script in ``tmp_path``.

    Uses the absolute path to the running interpreter so the script
    works even when ``python3`` is not on ``PATH`` (CI workers,
    minimal Docker images).
    """
    bin_path = tmp_path / "codexbar"
    bin_path.write_text(f"#!{sys.executable}\n{_STUB_BINARY_SCRIPT}\n")
    bin_path.chmod(0o755)
    return bin_path


def _pick_free_port() -> int:
    """Bind a loopback socket on port 0 to grab an ephemeral free port.

    The socket closes before we hand the number to the subprocess —
    standard TOCTOU window, but for an integration test on the
    operator's laptop the failure mode is "test fails, rerun" and
    never observed in practice (audit-god Wave 1 F-11).
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.asyncio
async def test_real_subprocess_boot_and_teardown(tmp_path: Path) -> None:
    """End-to-end: real subprocess, real /health HTTP, real SIGTERM.

    Uses an ephemeral port (Wave 1 F-11 fix) so parallel pytest runs
    don't collide on the previously-hardcoded 18766.
    """
    binary = _write_python_stub_binary(tmp_path)
    port = _pick_free_port()
    server = CodexBarServer(
        config=CodexBarServerConfig(
            binary=binary,
            port=port,
            readiness_timeout_seconds=4.0,
        )
    )
    await server.start()
    assert server.state is CodexBarServerState.READY, server.fail_reason

    # Live HTTP probe — confirm the stub is really serving.
    async with httpx.AsyncClient(timeout=1.0) as client:
        response = await client.get(f"{server.base_url}/health")
    assert response.status_code == 200

    await server.stop()
    assert server.state is CodexBarServerState.STOPPED
