"""Pydantic response schemas for the dashboard HTTP API.

Every schema represents a structure that's already on disk somewhere —
we never invent data. The endpoint code reads the real artifact, maps
it into one of these schemas, and returns it.

Per ``project_ui_stack.md`` ABSOLUTE no-mock rule: there's no schema
for any pillar/feature that doesn't yet have a backend artifact.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

__all__ = [
    "AuditEvent",
    "CardCreatePayload",
    "CardMovePayload",
    "CardUpdatePayload",
    "KanbanCardResponse",
    "KanbanResponse",
    "PausedSession",
    "PlanSnapshot",
    "ProjectCreatePayload",
    "ProjectResponse",
    "RecentSession",
    "RunRequestPayload",
    "RunRequestResponse",
    "WorkspaceEntry",
]


class _StrictResponse(BaseModel):
    """Forbid extra fields so accidental drift between schema + audit
    record JSON shapes fails loudly in tests instead of silently."""

    model_config = ConfigDict(extra="forbid")


class PausedSession(_StrictResponse):
    """One row in ``GET /api/sessions/paused``.

    Source-of-truth: a JSON file under ``~/.selffork/scheduled/``
    (one per paused session). See
    :class:`selffork_orchestrator.resume.store.ScheduledResume`.
    """

    session_id: str
    scheduled_at: datetime
    resume_at: datetime
    cli_agent: str
    config_path: str | None
    prd_path: str
    workspace_path: str
    reason: str
    kind: str
    is_due: bool


class RecentSession(_StrictResponse):
    """One row in ``GET /api/sessions/recent``.

    Source-of-truth: ``~/.selffork/audit/<session_id>.jsonl`` mtime,
    last ``session.state`` event in the file, optional ``agent.done``
    or ``error`` markers.
    """

    session_id: str
    started_at: datetime
    last_event_at: datetime
    final_state: str | None  # last observed state, e.g. "completed", "paused_rate_limit"
    rounds_observed: int
    cli_agent: str | None  # parsed from agent.invoke.binary if seen


class AuditEvent(_StrictResponse):
    """One audit-log line, raw."""

    ts: datetime
    category: str
    level: str
    event: str
    payload: dict[str, object]


class PlanSnapshot(_StrictResponse):
    """The current ``.selffork/plan.json`` for one session.

    Source-of-truth: workspace plan-as-state file. Schema mirrors
    :class:`selffork_orchestrator.plan.model.Plan`.
    """

    schema_version: int
    summary: str
    sub_tasks: list[dict[str, object]]


class WorkspaceEntry(_StrictResponse):
    """One node in the per-session workspace file tree."""

    path: str  # relative to workspace root
    kind: str  # "file" | "dir"
    size_bytes: int | None
    modified_at: datetime | None


class RunRequestPayload(BaseModel):
    """Body of ``POST /api/sessions/run``.

    The PRD must already exist on disk; we don't accept inline text in
    MVP (avoids mid-flight file management for the orchestrator).
    """

    prd_path: str
    config_path: str | None = None
    project_slug: str | None = None


class ProjectResponse(_StrictResponse):
    """One row in ``GET /api/projects`` (and the body of ``GET /api/projects/<slug>``)."""

    slug: str
    name: str
    description: str
    root_path: str | None
    created_at: datetime
    updated_at: datetime
    card_counts: dict[str, int]


class ProjectCreatePayload(BaseModel):
    """Body of ``POST /api/projects``. ``slug`` is normalised server-side."""

    name: str
    description: str = ""
    root_path: str | None = None


class KanbanCardResponse(_StrictResponse):
    id: str
    title: str
    body: str
    column: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    last_touched_by_session_id: str | None
    order: int | None


class KanbanResponse(_StrictResponse):
    """Body of ``GET /api/projects/<slug>/kanban``."""

    schema_version: int
    columns: list[str]
    cards_by_column: dict[str, list[KanbanCardResponse]]


class CardCreatePayload(BaseModel):
    title: str
    body: str = ""
    column: str = "backlog"
    order: int | None = None


class CardMovePayload(BaseModel):
    to_column: str


class CardUpdatePayload(BaseModel):
    title: str | None = None
    body: str | None = None
    order: int | None = None


class RunRequestResponse(_StrictResponse):
    """Response from ``POST /api/sessions/run``.

    The session_id is best-effort — we spawn a subprocess that mints
    its own ULID; we read it back from the spawned audit dir mtime
    once the child has touched its file. ``status="started"`` means
    the subprocess was launched; ``"failed_to_spawn"`` means we
    never got past ``subprocess.Popen``.
    """

    status: str
    pid: int | None
    detail: str | None
