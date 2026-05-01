"""Plan-as-state document model + store adapters.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.4.
"""

from __future__ import annotations

from selffork_orchestrator.plan.factory import build_plan_store
from selffork_orchestrator.plan.model import Plan, SubTask, SubTaskState
from selffork_orchestrator.plan.store_base import PlanStore
from selffork_orchestrator.plan.store_filesystem import FilesystemPlanStore

__all__ = [
    "FilesystemPlanStore",
    "Plan",
    "PlanStore",
    "SubTask",
    "SubTaskState",
    "build_plan_store",
]
