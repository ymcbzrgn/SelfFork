"""AndroidWorld task runner — scaffold harness.

Drives the autonomous loop against each task, captures a snapshot at
completion (or timeout), and scores via the task's ``success_check``.
Faz 1 ships the harness contract + a stub-friendly execution path;
real driver wiring lands when the orchestrator gets an AndroidWorld
mode flag (M7 prep).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from selffork_orchestrator.eval.android_world.tasks import (
    TASK_REGISTRY,
    AndroidWorldTask,
)

__all__ = [
    "AndroidWorldRunResult",
    "AndroidWorldRunner",
    "TaskOutcome",
]


@dataclass(slots=True)
class TaskOutcome:
    """Per-task outcome of an AndroidWorld harness run."""

    task_name: str
    succeeded: bool
    duration_seconds: float
    snapshot: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(slots=True)
class AndroidWorldRunResult:
    """Aggregate result of running a batch of AndroidWorld tasks."""

    outcomes: list[TaskOutcome]

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def passed(self) -> int:
        return sum(1 for o in self.outcomes if o.succeeded)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def as_report(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "pass_rate": self.pass_rate,
            "outcomes": [
                {
                    "task": o.task_name,
                    "succeeded": o.succeeded,
                    "duration_seconds": o.duration_seconds,
                    "error": o.error,
                }
                for o in self.outcomes
            ],
        }


class TaskExecutor(Protocol):
    """Strategy for running a single task end-to-end.

    Production implementations drive the autonomous Self Jr loop;
    tests pass a stub that returns a deterministic snapshot.
    """

    async def __call__(self, task: AndroidWorldTask) -> dict[str, Any]: ...


class AndroidWorldRunner:
    """Run a batch of AndroidWorld scaffold tasks and score them."""

    def __init__(
        self,
        executor: TaskExecutor,
        *,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._executor = executor
        self._timeout = timeout_seconds

    async def run_one(self, task: AndroidWorldTask) -> TaskOutcome:
        started = time.monotonic()
        try:
            snapshot = await asyncio.wait_for(
                self._executor(task),
                timeout=self._timeout,
            )
        except TimeoutError:
            return TaskOutcome(
                task_name=task.name,
                succeeded=False,
                duration_seconds=time.monotonic() - started,
                error="timeout",
            )
        except Exception as exc:
            return TaskOutcome(
                task_name=task.name,
                succeeded=False,
                duration_seconds=time.monotonic() - started,
                error=f"{type(exc).__name__}: {exc}",
            )
        check = task.success_check
        succeeded = bool(check(snapshot)) if check is not None else False
        return TaskOutcome(
            task_name=task.name,
            succeeded=succeeded,
            duration_seconds=time.monotonic() - started,
            snapshot=snapshot,
        )

    async def run_all(
        self,
        tasks: list[AndroidWorldTask] | None = None,
    ) -> AndroidWorldRunResult:
        active = tasks if tasks is not None else list(TASK_REGISTRY.values())
        outcomes: list[TaskOutcome] = []
        for task in active:
            outcomes.append(await self.run_one(task))
        return AndroidWorldRunResult(outcomes=outcomes)
