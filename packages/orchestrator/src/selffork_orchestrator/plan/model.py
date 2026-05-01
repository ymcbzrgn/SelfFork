"""Plan-as-state document data model.

Inspired by `prior art in the agentic-CLI orchestration space`.

A :class:`Plan` is a shared file the CLI agent reads and updates as it
works. SelfFork writes the initial plan at session start; the agent
manipulates sub-tasks via its own file-edit tools (no special API).

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.4.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Plan", "SubTask", "SubTaskState"]


class SubTaskState(StrEnum):
    """Lifecycle of a single sub-task."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    ABANDONED = "abandoned"


class SubTask(BaseModel):
    """A single unit of work the agent should complete."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str = ""
    expected_outcome: str = ""
    state: SubTaskState = SubTaskState.TODO
    notes: str = ""
    updated_at: datetime | None = None


class Plan(BaseModel):
    """Top-level plan document persisted by :class:`PlanStore`."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    prd_path: str
    created_at: datetime
    updated_at: datetime
    subtasks: list[SubTask] = Field(default_factory=list)

    @classmethod
    def new(
        cls,
        *,
        session_id: str,
        prd_path: str,
        subtasks: list[SubTask] | None = None,
    ) -> Self:
        """Create a fresh plan with ``created_at`` and ``updated_at`` set to now."""
        now = datetime.now(UTC)
        return cls(
            session_id=session_id,
            prd_path=prd_path,
            created_at=now,
            updated_at=now,
            subtasks=subtasks or [],
        )

    def find_subtask(self, subtask_id: str) -> SubTask | None:
        """Return the sub-task with ``id == subtask_id`` or ``None``."""
        for subtask in self.subtasks:
            if subtask.id == subtask_id:
                return subtask
        return None
