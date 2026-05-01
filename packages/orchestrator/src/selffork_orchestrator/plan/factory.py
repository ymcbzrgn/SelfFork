"""Backend → implementation resolver for :class:`PlanStore`."""

from __future__ import annotations

from collections.abc import Mapping

from selffork_orchestrator.plan.store_base import PlanStore
from selffork_orchestrator.plan.store_filesystem import FilesystemPlanStore
from selffork_orchestrator.plan.store_git import GitPlanStore
from selffork_shared.config import PlanConfig

__all__ = ["build_plan_store"]


_BACKENDS: Mapping[str, type[PlanStore]] = {
    "filesystem": FilesystemPlanStore,
    "git": GitPlanStore,
}


def build_plan_store(config: PlanConfig, workspace_path: str) -> PlanStore:
    """Return a fresh :class:`PlanStore` for ``config.backend``.

    Stubbed backends (``git`` in MVP v0) raise :class:`NotImplementedError`
    from their constructor; this function lets that propagate.
    """
    cls = _BACKENDS.get(config.backend)
    if cls is None:
        # Unreachable: ``config.backend`` is a Pydantic Literal.
        raise ValueError(f"unknown plan backend: {config.backend!r}")
    return cls(config, workspace_path)
