"""GitPlanStore — planned stub.

Implementation lands in **M2+** per ADR-001 §15 (version-tracked plan
history co-resident with the agent's git workspace). Until then,
instantiating this raises :class:`NotImplementedError` so a
``plan.backend='git'`` config fails fast with a clear message.
"""

from __future__ import annotations

from selffork_orchestrator.plan.model import Plan, SubTaskState
from selffork_orchestrator.plan.store_base import PlanStore
from selffork_shared.config import PlanConfig

__all__ = ["GitPlanStore"]


class GitPlanStore(PlanStore):
    """Stub. Not implemented in MVP v0."""

    def __init__(self, config: PlanConfig, workspace_path: str) -> None:
        raise NotImplementedError(
            "GitPlanStore is planned for M2+. See ADR-001 §15. "
            "For MVP, set plan.backend='filesystem'.",
        )

    async def load(self) -> Plan:  # pragma: no cover
        raise NotImplementedError

    async def save(self, plan: Plan) -> None:  # pragma: no cover
        raise NotImplementedError

    async def update_subtask_state(
        self,
        subtask_id: str,
        new_state: SubTaskState,
        notes: str | None = None,
    ) -> Plan:  # pragma: no cover
        raise NotImplementedError
