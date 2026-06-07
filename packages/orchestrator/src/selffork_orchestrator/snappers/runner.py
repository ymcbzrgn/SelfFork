"""SnapperRunner — async lifecycle for a fleet of Snappers.

Pattern:
- One :class:`Snapper` per CLI agent (claude-code, codex, gemini-cli, opencode, ...)
- Each runs at its own cadence (default 1s for Claude statusline; 5s for SQLite poll)
- Each tick: ``snapshot()`` → atomic write to ``~/.selffork/cli-state/<cli_id>.json``
- On transient failures (return None or exception): log + skip; loop survives.

Uses anyio TaskGroup so the runner cooperates with the main SelfFork event
loop (FastAPI / cli.py / lifecycle.session) — same async runtime.

Lifecycle:

  >>> runner = SnapperRunner(build_default_snappers())
  >>> async with anyio.create_task_group() as tg:
  ...     tg.start_soon(runner.serve)
  ...     # main work...
  ...     runner.stop()

Or use as a daemon entry point: ``await runner.serve()`` blocks forever
(or until another task signals ``runner.stop()``).
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import anyio

from selffork_orchestrator.snappers.base import (
    Snapper,
    atomic_write_json,
    snapshot_path,
)
from selffork_orchestrator.snappers.factory import build_default_snappers
from selffork_shared.logging import get_logger

__all__ = [
    "DEFAULT_SIDECAR_INTERVAL_SECONDS",
    "SnapperRunner",
    "SnapperRunnerConfig",
    "build_default_snapper_runner",
]

DEFAULT_SIDECAR_INTERVAL_SECONDS: Final[float] = 5.0
"""Dashboard sidecar tick cadence (override:
``SELFFORK_SNAPPER_RUNNER_DEFAULT_INTERVAL_SECONDS``).

Slower than the per-session 1 Hz default because dashboard consumers
(Connections, Home quota gauges) only refresh on tab switch / poll;
hammering each on-disk source at 1 Hz for hours is wasteful when the
proactive reader's staleness gate is 300 s anyway.
"""

_LOG = get_logger("selffork.snappers.runner")


@dataclass(frozen=True, slots=True)
class SnapperRunnerConfig:
    """Static configuration for :class:`SnapperRunner`.

    Attributes:
        intervals_seconds: Per-cli refresh cadence override map.
            Keys are ``cli_id``; missing keys use ``default_interval_seconds``.
        state_dir: Output directory; defaults to ``~/.selffork/cli-state/``.
        default_interval_seconds: Refresh cadence for snappers without an
            explicit ``intervals_seconds`` entry. 1.0s matches Claude
            statusline cadence; opencode's SQLite poll is comfortable at this rate.
        backoff_seconds: Wait after a hard error before retrying that snapper.
            Hard errors (raised exceptions) are rare; transient empty signals
            return None and resume on the next normal tick.
    """

    intervals_seconds: Mapping[str, float] = field(default_factory=dict)
    state_dir: Path | None = None
    default_interval_seconds: float = 1.0
    backoff_seconds: float = 5.0


class SnapperRunner:
    """Async runner for a fleet of :class:`Snapper` instances.

    Args:
        snappers: List of fully constructed snappers (typically from
            :func:`selffork_orchestrator.snappers.factory.build_default_snappers`).
        config: Optional runner config; defaults to ``SnapperRunnerConfig()``.
    """

    def __init__(
        self,
        snappers: list[Snapper],
        config: SnapperRunnerConfig | None = None,
    ) -> None:
        self._snappers = list(snappers)
        self._config = config if config is not None else SnapperRunnerConfig()
        self._stop_event = anyio.Event()

    @property
    def snappers(self) -> tuple[Snapper, ...]:
        return tuple(self._snappers)

    @property
    def config(self) -> SnapperRunnerConfig:
        return self._config

    def stop(self) -> None:
        """Signal :meth:`serve` to exit. Safe to call from any task."""
        self._stop_event.set()

    async def serve(self) -> None:
        """Run all snappers until :meth:`stop` is called.

        Each snapper runs in its own structured task; the runner exits when
        ``stop()`` fires and the cancel scope tears down all child tasks.
        Any exception inside a snapper loop is caught, logged, and the
        loop continues — one bad snapper never kills the fleet.
        """
        async with anyio.create_task_group() as tg:
            for snapper in self._snappers:
                tg.start_soon(self._loop, snapper)
            await self._stop_event.wait()
            tg.cancel_scope.cancel()
        # Best-effort resource cleanup after cancellation.
        for snapper in self._snappers:
            with contextlib.suppress(Exception):
                await snapper.aclose()

    async def _loop(self, snapper: Snapper) -> None:
        interval = self._config.intervals_seconds.get(
            snapper.cli_id,
            self._config.default_interval_seconds,
        )
        path = snapshot_path(snapper.cli_id, state_dir=self._config.state_dir)
        while not self._stop_event.is_set():
            try:
                snap = await snapper.snapshot()
            except Exception as exc:
                _LOG.warning(
                    "snapper.error",
                    cli=snapper.cli_id,
                    error=str(exc),
                )
                await self._sleep_with_stop(self._config.backoff_seconds)
                continue
            if snap is not None:
                try:
                    atomic_write_json(path, snap)
                except OSError as exc:
                    _LOG.warning(
                        "snapper.write_failed",
                        cli=snapper.cli_id,
                        error=str(exc),
                        path=str(path),
                    )
            await self._sleep_with_stop(interval)

    async def _sleep_with_stop(self, seconds: float) -> None:
        if seconds <= 0:
            return
        with anyio.move_on_after(seconds):
            await self._stop_event.wait()


# ── factory ────────────────────────────────────────────────────────────


def _resolve_default_interval() -> float:
    raw = os.environ.get("SELFFORK_SNAPPER_RUNNER_DEFAULT_INTERVAL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_SIDECAR_INTERVAL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_SIDECAR_INTERVAL_SECONDS
    return max(0.25, value)


def _resolve_state_dir() -> Path | None:
    raw = os.environ.get("SELFFORK_SNAPPER_RUNNER_STATE_DIR", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def build_default_snapper_runner() -> SnapperRunner | None:
    """Build the dashboard-side :class:`SnapperRunner` from env.

    Returns ``None`` when explicitly disabled via
    ``SELFFORK_SNAPPER_RUNNER_ENABLED=false`` (or ``"0"`` / ``"no"``);
    the dashboard lifespan skips boot in that case so a host without
    the per-CLI on-disk surfaces (CI container, fresh dev box) does
    not waste cycles probing missing paths every interval.

    Wave 2 default is **opt-out** — auto-boot whenever the dashboard
    is up so the Connections + Home quota gauges populate without
    a manual snapper invocation. Mirrors the CodexBar sidecar policy
    (`build_default_codexbar_server`).

    Cadence is governed by
    ``SELFFORK_SNAPPER_RUNNER_DEFAULT_INTERVAL_SECONDS`` (default 5 s);
    state dir by ``SELFFORK_SNAPPER_RUNNER_STATE_DIR`` (default
    ``~/.selffork/cli-state/``).
    """
    enabled_raw = os.environ.get("SELFFORK_SNAPPER_RUNNER_ENABLED", "").strip().lower()
    if enabled_raw in {"false", "0", "no"}:
        return None
    snappers = build_default_snappers()
    config = SnapperRunnerConfig(
        default_interval_seconds=_resolve_default_interval(),
        state_dir=_resolve_state_dir(),
    )
    return SnapperRunner(snappers=snappers, config=config)
