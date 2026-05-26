"""AndroidWorld eval harness scaffold (S-ToolFleet Faz 1).

Apache-2.0 adopt-style port of google-research/android_world's task
runner — minimal subset that lets SelfFork run a fixed set of mobile
tasks against the autonomous loop + score completion. Faz 1 ships the
SCAFFOLD only: 3-5 happy-path tasks defined, runner harness wired,
scoring report emitted. Full 116-task adoption lives in M7 prep.

Reference: examples_crucial/mobile-use (mobile-use's 100% AndroidWorld
completion claim; our scaffold mirrors their task definition shape).
"""

from __future__ import annotations

from selffork_orchestrator.eval.android_world.runner import (
    AndroidWorldRunner,
    AndroidWorldRunResult,
    TaskOutcome,
)
from selffork_orchestrator.eval.android_world.tasks import (
    TASK_REGISTRY,
    AndroidWorldTask,
    list_tasks,
)

__all__ = [
    "TASK_REGISTRY",
    "AndroidWorldRunResult",
    "AndroidWorldRunner",
    "AndroidWorldTask",
    "TaskOutcome",
    "list_tasks",
]
