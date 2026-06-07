"""Auto Dream — threshold-gated GLOBAL pool reflection pipeline (ADR-009 §4).

ADR-002 §11 four-phase pipeline (Orientation → Gather Signal → Consolidation
→ Prune & Index) is **already implemented** by the Order 5 Reflector
(:class:`selffork_mind.memory.tiers.reflection.Reflector`, deterministic-first).
This module wraps the runner with:

1. **Threshold gate** — 4 conditions must all hold before a dream runs:

   * ``hours_since_last_dream >= 24`` (Anthropic Auto Dream spec).
   * ``sessions_since_last_dream >= 5`` (Anthropic Auto Dream spec).
   * Not rate-limited (Heartbeat's quota signal).
   * Idle (no active task in the last N minutes, default 5).

   Failing any condition returns ``None`` from :meth:`AutoDreamRunner.maybe_run`
   without touching the underlying Reflector — cheap repeated calls from the
   Heartbeat tick are the design point.

2. **GLOBAL pool routing.** Reflection lives in the GLOBAL pool (ADR-009 §3
   T-pool mapping); Auto Dream consumes the operator's cross-project facts
   and produces cross-project lessons, not project-bound ones.

3. **Checkpoint persistence.** ``~/.selffork/global/mind/reflection/dream-checkpoint.json``
   tracks ``last_dream_at`` + ``sessions_since_last_dream`` so restarts
   resume the gate state.

The Heartbeat tick wires this via:

    runner = AutoDreamRunner(reflector=global_reflector, ...)
    result = await runner.maybe_run(world_state)
    if result is not None:
        audit_writer.write(build_audit_entry(action="AUTO_DREAM_RUN", ...))
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from selffork_mind.memory.tiers.reflection import ReflectionReport, Reflector

__all__ = [
    "AutoDreamCheckpoint",
    "AutoDreamConfig",
    "AutoDreamGate",
    "AutoDreamReport",
    "AutoDreamRunner",
    "GateDecision",
    "load_dream_checkpoint",
    "save_dream_checkpoint",
]


_log = logging.getLogger(__name__)


# ── configuration ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AutoDreamConfig:
    """Threshold knobs for the Auto Dream gate.

    Defaults match the Anthropic Auto Dream spec (2026-05-06 research
    preview, https://claudefa.st/blog/guide/mechanics/auto-dream):

    * ``hours_threshold = 24`` — at least one calendar day between runs.
    * ``sessions_threshold = 5`` — five new sessions of accumulated signal.
    * ``idle_minutes = 5`` — operator hasn't touched the system recently.

    Operators can tighten or loosen these for testing without recompiling
    by passing custom values to :class:`AutoDreamRunner`.
    """

    hours_threshold: float = 24.0
    sessions_threshold: int = 5
    idle_minutes: float = 5.0

    def __post_init__(self) -> None:
        if self.hours_threshold < 0:
            raise ValueError("hours_threshold must be ≥ 0")
        if self.sessions_threshold < 0:
            raise ValueError("sessions_threshold must be ≥ 0")
        if self.idle_minutes < 0:
            raise ValueError("idle_minutes must be ≥ 0")


# ── checkpoint ─────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AutoDreamCheckpoint:
    """Persistent state across daemon restarts."""

    last_dream_at: datetime | None = None
    sessions_since_last_dream: int = 0
    last_reflections_written: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "last_dream_at": (self.last_dream_at.isoformat() if self.last_dream_at else None),
            "sessions_since_last_dream": self.sessions_since_last_dream,
            "last_reflections_written": self.last_reflections_written,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AutoDreamCheckpoint:
        last_raw = data.get("last_dream_at")
        last: datetime | None = None
        if isinstance(last_raw, str):
            with suppress(ValueError):
                last = datetime.fromisoformat(last_raw)
        sessions_raw = data.get("sessions_since_last_dream", 0)
        sessions = int(sessions_raw) if isinstance(sessions_raw, (int, float, str)) else 0
        written_raw = data.get("last_reflections_written", 0)
        written = int(written_raw) if isinstance(written_raw, (int, float, str)) else 0
        return cls(
            last_dream_at=last,
            sessions_since_last_dream=sessions,
            last_reflections_written=written,
        )


def load_dream_checkpoint(path: Path) -> AutoDreamCheckpoint:
    if not path.is_file():
        return AutoDreamCheckpoint()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _log.warning("dream_checkpoint_load_failed path=%s", path)
        return AutoDreamCheckpoint()
    if not isinstance(data, dict):
        return AutoDreamCheckpoint()
    return AutoDreamCheckpoint.from_dict(data)


def save_dream_checkpoint(path: Path, checkpoint: AutoDreamCheckpoint) -> None:
    """Atomic write — temp + rename, mirrors S-Auto Faz E pattern."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(checkpoint.to_dict()), encoding="utf-8")
    os.replace(tmp, path)


# ── gate decision ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GateDecision:
    """One gate evaluation — useful for telemetry + tests.

    ``should_run`` is the final verdict; ``failed_conditions`` lists every
    threshold that prevented the run (empty when ``should_run`` is True).
    """

    should_run: bool
    failed_conditions: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.should_run


# ── gate ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AutoDreamGate:
    """Pure evaluator — no side effects, deterministic."""

    config: AutoDreamConfig

    def evaluate(
        self,
        *,
        checkpoint: AutoDreamCheckpoint,
        now: datetime,
        rate_limited: bool,
        last_activity_at: datetime | None,
    ) -> GateDecision:
        """Evaluate all four conditions.

        ``last_activity_at`` is the timestamp of the operator's most recent
        action; pass ``None`` to disable the idle check (test mode).

        Returns a :class:`GateDecision` whose ``should_run`` is True only
        when every condition passes.
        """
        failed: list[str] = []

        # 1. Hours since last dream.
        if checkpoint.last_dream_at is not None:
            elapsed = now - checkpoint.last_dream_at
            if elapsed < timedelta(hours=self.config.hours_threshold):
                hours_left = (
                    timedelta(hours=self.config.hours_threshold) - elapsed
                ).total_seconds() / 3600.0
                failed.append(f"hours_remaining={hours_left:.2f}")

        # 2. Sessions accumulated.
        if checkpoint.sessions_since_last_dream < self.config.sessions_threshold:
            failed.append(
                f"sessions_short={checkpoint.sessions_since_last_dream}"
                f"/{self.config.sessions_threshold}",
            )

        # 3. Not rate-limited.
        if rate_limited:
            failed.append("rate_limited")

        # 4. Idle — last activity ≥ idle_minutes ago.
        if last_activity_at is not None:
            idle_for = now - last_activity_at
            if idle_for < timedelta(minutes=self.config.idle_minutes):
                failed.append(
                    f"active_within={(idle_for.total_seconds() / 60.0):.1f}min",
                )

        return GateDecision(
            should_run=not failed,
            failed_conditions=tuple(failed),
        )


# ── report ─────────────────────────────────────────────────────────────


@dataclass
class AutoDreamReport:
    """Outcome of one pipeline run (gate-passed path)."""

    started_at: datetime
    finished_at: datetime
    reflection: ReflectionReport
    new_checkpoint: AutoDreamCheckpoint

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    def to_payload(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "reflection": self.reflection.to_payload(),
            "new_checkpoint": self.new_checkpoint.to_dict(),
        }


# ── runner ─────────────────────────────────────────────────────────────


SessionsCounter = Callable[[], Awaitable[int]]
"""Optional async callable that returns the *delta* of sessions since
the last successful dream.

When omitted, :class:`AutoDreamRunner` falls back to the checkpoint's
internal counter (which is incremented manually by the orchestrator via
:meth:`AutoDreamRunner.bump_sessions`).
"""


@dataclass
class AutoDreamRunner:
    """Threshold-gated Auto Dream orchestrator.

    Construct one runner per GLOBAL pool. The Heartbeat tick calls
    :meth:`maybe_run` on every iteration; the gate makes that cheap.

    Wire (Heartbeat side):

        runner = AutoDreamRunner(
            reflector=global_reflector,
            checkpoint_path=Path("~/.selffork/global/mind/reflection/dream-checkpoint.json").expanduser(),
        )

        # In the heartbeat tick:
        report = await runner.maybe_run(
            now=datetime.now(UTC),
            rate_limited=world_state.is_rate_limited,
            last_activity_at=world_state.last_activity_at,
            project_slug=None,  # GLOBAL pool
        )
        if report is not None:
            audit_writer.write(build_audit_entry(
                action="AUTO_DREAM_RUN",
                result_metadata=report.to_payload(),
            ))
    """

    reflector: Reflector
    checkpoint_path: Path
    config: AutoDreamConfig = field(default_factory=AutoDreamConfig)
    sessions_counter: SessionsCounter | None = None
    _gate: AutoDreamGate = field(init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self._gate = AutoDreamGate(config=self.config)

    # ── public surface ─────────────────────────────────────────────────

    async def maybe_run(
        self,
        *,
        now: datetime | None = None,
        rate_limited: bool = False,
        last_activity_at: datetime | None = None,
        project_slug: str | None = None,
    ) -> AutoDreamReport | None:
        """Evaluate the gate; run the pipeline iff every condition passes."""
        async with self._lock:
            current = now or datetime.now(UTC)
            checkpoint = await self._load_checkpoint_with_sessions()
            decision = self._gate.evaluate(
                checkpoint=checkpoint,
                now=current,
                rate_limited=rate_limited,
                last_activity_at=last_activity_at,
            )
            if not decision.should_run:
                _log.debug(
                    "auto_dream_gate_blocked failed=%s",
                    ",".join(decision.failed_conditions),
                )
                return None

            started = current
            reflection_report = await self.reflector.reflect(
                project_slug=project_slug,
            )
            finished = datetime.now(UTC)

            new_checkpoint = AutoDreamCheckpoint(
                last_dream_at=started,
                sessions_since_last_dream=0,
                last_reflections_written=reflection_report.reflections_written,
            )
            await asyncio.to_thread(
                save_dream_checkpoint,
                self.checkpoint_path,
                new_checkpoint,
            )
            return AutoDreamReport(
                started_at=started,
                finished_at=finished,
                reflection=reflection_report,
                new_checkpoint=new_checkpoint,
            )

    async def force_run(
        self,
        *,
        project_slug: str | None = None,
    ) -> AutoDreamReport:
        """Bypass the gate — used by ``selffork mind dream --force``."""
        async with self._lock:
            started = datetime.now(UTC)
            reflection_report = await self.reflector.reflect(project_slug=project_slug)
            finished = datetime.now(UTC)
            new_checkpoint = AutoDreamCheckpoint(
                last_dream_at=started,
                sessions_since_last_dream=0,
                last_reflections_written=reflection_report.reflections_written,
            )
            await asyncio.to_thread(
                save_dream_checkpoint,
                self.checkpoint_path,
                new_checkpoint,
            )
            return AutoDreamReport(
                started_at=started,
                finished_at=finished,
                reflection=reflection_report,
                new_checkpoint=new_checkpoint,
            )

    async def evaluate_gate(
        self,
        *,
        now: datetime | None = None,
        rate_limited: bool = False,
        last_activity_at: datetime | None = None,
    ) -> GateDecision:
        """Public gate evaluation — useful for telemetry without running."""
        current = now or datetime.now(UTC)
        checkpoint = await self._load_checkpoint_with_sessions()
        return self._gate.evaluate(
            checkpoint=checkpoint,
            now=current,
            rate_limited=rate_limited,
            last_activity_at=last_activity_at,
        )

    async def bump_sessions(self, delta: int = 1) -> AutoDreamCheckpoint:
        """Increment the sessions-since-last-dream counter atomically."""
        async with self._lock:
            assert self.checkpoint_path is not None  # noqa: S101
            current = await asyncio.to_thread(load_dream_checkpoint, self.checkpoint_path)
            updated = AutoDreamCheckpoint(
                last_dream_at=current.last_dream_at,
                sessions_since_last_dream=max(
                    0,
                    current.sessions_since_last_dream + delta,
                ),
                last_reflections_written=current.last_reflections_written,
            )
            await asyncio.to_thread(
                save_dream_checkpoint,
                self.checkpoint_path,
                updated,
            )
            return updated

    # ── helpers ────────────────────────────────────────────────────────

    async def _load_checkpoint_with_sessions(self) -> AutoDreamCheckpoint:
        """Load the checkpoint, optionally refreshing the sessions counter."""
        base = await asyncio.to_thread(load_dream_checkpoint, self.checkpoint_path)
        if self.sessions_counter is None:
            return base
        try:
            delta = await self.sessions_counter()
        except Exception:
            _log.exception("auto_dream_sessions_counter_failed")
            return base
        return AutoDreamCheckpoint(
            last_dream_at=base.last_dream_at,
            sessions_since_last_dream=max(0, int(delta)),
            last_reflections_written=base.last_reflections_written,
        )
