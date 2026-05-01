"""PlanStore ABC.

One instance per session; the workspace path is fixed at construction.
The agent reads/writes the plan file directly via its own file tools — the
orchestrator uses the store mainly to seed the initial plan and read the
final state.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.4.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from selffork_orchestrator.plan.model import Plan, SubTaskState
from selffork_shared.config import PlanConfig

__all__ = ["PlanStore"]


class PlanStore(ABC):
    """Persistent store for the plan-as-state document."""

    @abstractmethod
    def __init__(self, config: PlanConfig, workspace_path: str) -> None:
        """Initialise from config and the absolute workspace path on disk.

        Implementations must validate that ``config.backend`` matches the
        backend they implement, and raise :class:`ValueError` otherwise.
        """

    @abstractmethod
    async def load(self) -> Plan:
        """Load the current plan.

        Raises:
            selffork_shared.errors.PlanLoadError: file missing, malformed
                JSON, or schema validation failure.
        """

    @abstractmethod
    async def save(self, plan: Plan) -> None:
        """Persist ``plan`` atomically.

        Implementations must guarantee a partially-written plan never
        becomes visible to readers (temp-file + rename for the filesystem
        backend; equivalent for git).

        Raises:
            selffork_shared.errors.PlanSaveError: persistence failed.
        """

    @abstractmethod
    async def update_subtask_state(
        self,
        subtask_id: str,
        new_state: SubTaskState,
        notes: str | None = None,
    ) -> Plan:
        """Atomic single-subtask state transition; returns the updated plan.

        Raises:
            selffork_shared.errors.PlanLoadError: ``subtask_id`` not present
                in the plan, or plan not yet saved.
            selffork_shared.errors.PlanSaveError: write failed.
        """
