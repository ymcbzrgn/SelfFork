"""``codexbar serve`` sidecar lifecycle (S-Quota Faz B).

ADR-007 §4 S-Quota / `[[codexbar-adoption-2026-05-22]]` adapter shim:
CodexBar exposes its quota tracker over a tiny HTTP server
(``codexbar serve --port <p>``) bound to loopback. SelfFork owns the
process for its lifetime — boots it during the dashboard FastAPI
lifespan, probes ``GET /health`` for readiness, and SIGTERMs it on
shutdown.

Design constraints (ultrathink notes):

* **Graceful degradation is mandatory.** SelfFork must run when the
  binary is missing (CI box, fresh dev machine before ``make
  install-codexbar``, Linux self-host before the vendored install
  step). The dashboard lifespan calls :meth:`CodexBarServer.start`
  inside ``try/except``; a failure here logs and disables the sidecar
  — SelfFork's primary snappers handle the load alone.

* **Single owner.** We don't reuse an externally-started ``codexbar
  serve`` in Wave 1 (operator confusion + crash spirals). Operators
  who already have one running set
  ``SELFFORK_CODEXBAR_ENABLED=false`` and point the snappers at the
  external base URL via the snapper's ``base_url`` kwarg.

* **Async-native.** Uses :func:`asyncio.create_subprocess_exec` so the
  same lifespan that owns the PTB Application can ``await`` boot
  + teardown without thread context switches.

* **Test fixture parity.** Production spawns the real Swift binary;
  unit tests spawn a tiny Python aiohttp stub. The state machine
  + health-probe logic is identical in both cases — we just swap the
  resolved binary.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import signal
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import httpx

__all__ = [
    "DEFAULT_PORT",
    "DEFAULT_READINESS_TIMEOUT_SECONDS",
    "DEFAULT_REFRESH_INTERVAL_SECONDS",
    "CodexBarServer",
    "CodexBarServerConfig",
    "CodexBarServerState",
    "build_default_codexbar_server",
]

_log = logging.getLogger(__name__)


DEFAULT_PORT: Final[int] = 8766
"""Loopback port the dashboard binds ``codexbar serve`` to.

Distinct from the dashboard's own ``8765`` so the two run side-by-side
on a single host. Override with ``SELFFORK_CODEXBAR_PORT``.
"""

DEFAULT_REFRESH_INTERVAL_SECONDS: Final[int] = 60
"""Per-provider cache TTL inside ``codexbar serve``.

CodexBar's default is also 60s (`docs/cli.md`); we mirror it so the
SelfFork-side cadence (SnapperRunner ticks at 1 Hz) doesn't hammer
the upstream provider APIs.
"""

DEFAULT_READINESS_TIMEOUT_SECONDS: Final[float] = 8.0
"""Maximum time we wait for the sidecar to answer ``GET /health``.

The Swift binary cold-starts in ~0.5-2 s on macOS; allow generous
headroom for Linux + cold-cache scenarios before we mark boot failed.
"""

_READINESS_POLL_INTERVAL_SECONDS: Final[float] = 0.2
_TEARDOWN_GRACE_SECONDS: Final[float] = 3.0
_HEALTH_PROBE_TIMEOUT_SECONDS: Final[float] = 1.5


class CodexBarServerState(StrEnum):
    """Lifecycle states for :class:`CodexBarServer`.

    ``INACTIVE → STARTING → READY → STOPPING → STOPPED`` is the happy
    path; any health-probe / spawn failure transitions to ``FAILED``.
    """

    INACTIVE = "inactive"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CodexBarServerConfig:
    """Static config for one :class:`CodexBarServer` instance.

    Attributes:
        binary: Absolute path to the ``codexbar`` executable. ``None``
            disables the sidecar (caller skips :meth:`start`).
        port: Loopback port to bind. Operator override via
            ``SELFFORK_CODEXBAR_PORT``.
        refresh_interval_seconds: Forwarded as
            ``--refresh-interval``; upstream cache TTL.
        readiness_timeout_seconds: Max time we wait for the sidecar
            ``/health`` to respond before marking boot failed.
        extra_args: Additional CLI flags appended verbatim (escape
            hatch for advanced operators; tests use it to inject
            stub-specific switches).
    """

    binary: Path | None
    port: int = DEFAULT_PORT
    refresh_interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS
    readiness_timeout_seconds: float = DEFAULT_READINESS_TIMEOUT_SECONDS
    extra_args: tuple[str, ...] = ()


class CodexBarServer:
    """Async lifecycle wrapper around ``codexbar serve``.

    The instance is constructed eagerly (no side effects); ``start``
    actually spawns the binary and probes readiness. Both ``start``
    and ``stop`` are idempotent — calling either twice is safe.

    Usage::

        config = build_default_codexbar_server()
        if config.binary is None:
            _log.warning("codexbar binary not found; secondary source disabled")
        server = CodexBarServer(config=config)
        await server.start()  # transitions to READY or FAILED
        ...
        await server.stop()  # graceful SIGTERM with SIGKILL fallback
    """

    def __init__(
        self,
        *,
        config: CodexBarServerConfig,
        process_factory: Any | None = None,
        health_client_factory: Any | None = None,
    ) -> None:
        self._config = config
        self._state = CodexBarServerState.INACTIVE
        self._process: asyncio.subprocess.Process | None = None
        self._fail_reason: str | None = None
        # Indirection for tests: production uses
        # ``asyncio.create_subprocess_exec`` and a real httpx client;
        # tests substitute fakes that return canned objects.
        self._process_factory = (
            process_factory or self._default_process_factory
        )
        self._health_client_factory = (
            health_client_factory or self._default_health_client
        )

    # ── public API ────────────────────────────────────────────────────

    @property
    def state(self) -> CodexBarServerState:
        return self._state

    @property
    def port(self) -> int:
        return self._config.port

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._config.port}"

    @property
    def binary(self) -> Path | None:
        return self._config.binary

    @property
    def is_running(self) -> bool:
        return self._state is CodexBarServerState.READY

    @property
    def fail_reason(self) -> str | None:
        return self._fail_reason

    async def start(self) -> None:
        """Spawn the sidecar and block until ``/health`` is 200.

        No-op when the binary is unresolved or the server is already
        running. ``FAILED`` state on any spawn / readiness error —
        caller logs and continues (sidecar is best-effort).
        """
        if self._config.binary is None:
            self._state = CodexBarServerState.FAILED
            self._fail_reason = "codexbar binary not resolved"
            _log.warning("codexbar_sidecar_skipped", extra={"reason": self._fail_reason})
            return
        if self._state in (CodexBarServerState.READY, CodexBarServerState.STARTING):
            return
        self._state = CodexBarServerState.STARTING
        self._fail_reason = None

        argv = self._build_argv()
        try:
            self._process = await self._process_factory(argv)
        except FileNotFoundError as exc:
            self._fail(f"binary not executable: {exc}")
            return
        except OSError as exc:
            self._fail(f"spawn failed: {exc}")
            return

        try:
            ready = await self._await_readiness()
        except Exception as exc:
            self._fail(f"readiness probe crashed: {exc}")
            await self._terminate_process()
            return

        if not ready:
            # ``_await_readiness`` may have already populated
            # ``fail_reason`` with a more specific cause (e.g. process
            # exited mid-probe). Don't clobber it with the generic
            # "timed out" message.
            self._fail(self._fail_reason or "readiness probe timed out")
            await self._terminate_process()
            return

        self._state = CodexBarServerState.READY
        _log.info(
            "codexbar_sidecar_started",
            extra={
                "port": self._config.port,
                "binary": str(self._config.binary),
                "pid": self._process.pid if self._process else None,
            },
        )

    async def stop(self) -> None:
        """Send SIGTERM, wait, escalate to SIGKILL if still alive.

        Idempotent — calling on an already-stopped instance is a no-op.
        Always transitions the state to ``STOPPED`` (never back to
        ``FAILED``); diagnostic detail stays on :attr:`fail_reason` if
        the sidecar previously errored.
        """
        if self._process is None:
            self._state = CodexBarServerState.STOPPED
            return
        if self._state in (CodexBarServerState.STOPPED, CodexBarServerState.STOPPING):
            return
        self._state = CodexBarServerState.STOPPING
        await self._terminate_process()
        self._state = CodexBarServerState.STOPPED
        _log.info(
            "codexbar_sidecar_stopped",
            extra={"port": self._config.port},
        )

    # ── internals ─────────────────────────────────────────────────────

    def _fail(self, reason: str) -> None:
        self._fail_reason = reason
        self._state = CodexBarServerState.FAILED
        _log.warning(
            "codexbar_sidecar_failed",
            extra={"reason": reason, "port": self._config.port},
        )

    def _build_argv(self) -> Sequence[str]:
        assert self._config.binary is not None  # noqa: S101 — start() guards
        return (
            str(self._config.binary),
            "serve",
            "--port",
            str(self._config.port),
            "--refresh-interval",
            str(self._config.refresh_interval_seconds),
            *self._config.extra_args,
        )

    async def _default_process_factory(
        self, argv: Sequence[str]
    ) -> asyncio.subprocess.Process:
        # ``start_new_session=True`` puts the child in its own process
        # group so we can ``os.killpg`` the whole tree at teardown
        # (CodexBar may spawn helper processes for some providers).
        return await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )

    def _default_health_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=_HEALTH_PROBE_TIMEOUT_SECONDS)

    async def _await_readiness(self) -> bool:
        """Poll ``GET /health`` until 200 or the budget elapses."""
        deadline = (
            asyncio.get_event_loop().time()
            + self._config.readiness_timeout_seconds
        )
        last_error: str | None = None
        client = self._health_client_factory()
        try:
            while asyncio.get_event_loop().time() < deadline:
                # Surface fatal crashes early — a dead subprocess can't
                # answer health probes and we'd burn the whole budget
                # waiting.
                if self._process is not None and self._process.returncode is not None:
                    self._fail_reason = (
                        f"sidecar exited with code {self._process.returncode}"
                    )
                    return False
                try:
                    response = await client.get(f"{self.base_url}/health")
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout) as exc:
                    last_error = type(exc).__name__
                else:
                    if response.status_code == 200:
                        return True
                    last_error = f"http_{response.status_code}"
                await asyncio.sleep(_READINESS_POLL_INTERVAL_SECONDS)
        finally:
            await client.aclose()
        if last_error:
            _log.debug("codexbar_readiness_last_error", extra={"err": last_error})
        return False

    async def _terminate_process(self) -> None:
        proc = self._process
        if proc is None:
            return
        if proc.returncode is not None:
            self._process = None
            return
        with contextlib.suppress(ProcessLookupError, OSError):
            os.killpg(4242, signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=_TEARDOWN_GRACE_SECONDS)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError, OSError):
                os.killpg(4242, signal.SIGKILL)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), timeout=1.0)
        self._process = None


# ── factory ────────────────────────────────────────────────────────────


def _resolve_binary_path() -> Path | None:
    """Pick the ``codexbar`` binary based on env + PATH.

    Resolution order (first hit wins):
      1. ``SELFFORK_CODEXBAR_BIN`` — explicit override
      2. ``shutil.which("codexbar")`` — operator-installed (brew etc.)
      3. ``/usr/local/bin/codexbar`` — the vendored install path
         (``infra/deploy/scripts/install-codexbar.sh`` deposits there)

    Returns ``None`` when no path exists / is not executable.
    """
    override = os.environ.get("SELFFORK_CODEXBAR_BIN", "").strip()
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override).expanduser())
    which_path = shutil.which("codexbar")
    if which_path:
        candidates.append(Path(which_path))
    candidates.append(Path("/usr/local/bin/codexbar"))
    for candidate in candidates:
        try:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        except OSError:
            continue
    return None


def _resolve_port() -> int:
    raw = os.environ.get("SELFFORK_CODEXBAR_PORT", "").strip()
    if not raw:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_PORT
    if port <= 0 or port > 65535:
        return DEFAULT_PORT
    return port


def _resolve_refresh_interval() -> int:
    raw = os.environ.get("SELFFORK_CODEXBAR_REFRESH_INTERVAL", "").strip()
    if not raw:
        return DEFAULT_REFRESH_INTERVAL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_REFRESH_INTERVAL_SECONDS
    return max(1, value)


def _resolve_readiness_timeout() -> float:
    raw = os.environ.get("SELFFORK_CODEXBAR_READINESS_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_READINESS_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_READINESS_TIMEOUT_SECONDS
    return max(0.5, value)


def build_default_codexbar_server() -> CodexBarServer:
    """Construct the sidecar from the env (dashboard lifespan helper).

    Wave 2 default is **opt-out**: the sidecar auto-boots whenever a
    ``codexbar`` binary is resolvable on the host (env override, PATH,
    or ``/usr/local/bin/codexbar``). Wave 1 shipped opt-in only —
    audit-god #F-02 — because the dashboard had no consumer; the
    provider_router wire (Wave 2 Faz B) now reads the sidecar through
    :class:`CodexBarFallbackReader`, so auto-boot stops wasting cycles
    and starts paying its way.

    Env switches:

    * ``SELFFORK_CODEXBAR_ENABLED=false`` / ``"0"`` / ``"no"`` — hard
      disable, even when a binary is on the host. The returned
      instance has ``binary=None`` and :meth:`CodexBarServer.start`
      becomes a graceful no-op that logs ``codexbar_sidecar_skipped``.
    * ``SELFFORK_CODEXBAR_ENABLED=true`` / ``"1"`` / ``"yes"`` —
      explicit opt-in (forwards-compat with Wave 1 invocations; no
      effect today beyond the auto-detect default).
    * Anything else (unset, empty) — auto-detect: boot if a binary is
      found, gracefully skip otherwise.
    """
    enabled_raw = os.environ.get("SELFFORK_CODEXBAR_ENABLED", "").strip().lower()
    explicitly_disabled = enabled_raw in {"false", "0", "no"}
    binary = None if explicitly_disabled else _resolve_binary_path()
    return CodexBarServer(
        config=CodexBarServerConfig(
            binary=binary,
            port=_resolve_port(),
            refresh_interval_seconds=_resolve_refresh_interval(),
            readiness_timeout_seconds=_resolve_readiness_timeout(),
        )
    )
