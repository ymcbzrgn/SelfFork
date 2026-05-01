"""Project + KanbanBoard primitives.

Per ``project_project_model.md`` a Project is the first-class container
that owns a kanban board, sessions, and an optional bound user repo
path. The store is filesystem-backed under
``~/.selffork/projects/<slug>/``.
"""

from __future__ import annotations

from selffork_orchestrator.projects.model import (
    DEFAULT_COLUMNS,
    KanbanBoard,
    KanbanCard,
    KanbanColumn,
    Project,
    make_card_id,
)
from selffork_orchestrator.projects.slug import (
    MAX_SLUG_LEN,
    RESERVED_SLUGS,
    normalize_slug,
    validate_slug,
)
from selffork_orchestrator.projects.store import ProjectStore

__all__ = [
    "DEFAULT_COLUMNS",
    "MAX_SLUG_LEN",
    "RESERVED_SLUGS",
    "KanbanBoard",
    "KanbanCard",
    "KanbanColumn",
    "Project",
    "ProjectStore",
    "make_card_id",
    "normalize_slug",
    "validate_slug",
]
