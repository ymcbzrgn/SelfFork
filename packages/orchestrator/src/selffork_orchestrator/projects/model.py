"""Pydantic models for Project + KanbanBoard + KanbanCard.

These are the persisted shapes — every JSON file under
``~/.selffork/projects/<slug>/`` decodes into one of these dataclasses.
We use Pydantic (not bare dataclasses) so the schema doubles as the
HTTP response model and we get free validation on read + write.

Per ``project_project_model.md`` decisions:

- ``slug`` and ``name`` are required.
- ``root_path`` is optional. When set, ``selffork run --project <slug>``
  cwd's into that path (the user's repo) but still writes audit + plan
  state under the project's own dir.
- A board's columns are fixed at construction time. We DO NOT support
  arbitrary user-defined columns yet — the four stages cover every
  workflow we've been asked for, and tooling stays simpler with a
  closed set.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DEFAULT_COLUMNS",
    "KanbanBoard",
    "KanbanCard",
    "KanbanColumn",
    "Project",
    "make_card_id",
]

KanbanColumn = Literal["backlog", "in_progress", "review", "done"]

DEFAULT_COLUMNS: tuple[KanbanColumn, ...] = (
    "backlog",
    "in_progress",
    "review",
    "done",
)


class _Strict(BaseModel):
    """Forbid extra fields so a stale file format fails loudly instead
    of silently dropping data.
    """

    model_config = ConfigDict(extra="forbid")


def make_card_id() -> str:
    """Mint a card id. Uses ULID under the hood for sortability without
    pulling another dep — re-uses the orchestrator's existing helper.
    """
    from selffork_shared.ulid import new_ulid

    return f"card-{new_ulid()}"


class KanbanCard(_Strict):
    """One kanban card.

    ``column`` is the only mutable lifecycle bit; the rest of the
    fields stay stable across moves so the audit history (who created,
    when, what changed) reads cleanly.
    """

    id: str
    title: str
    body: str = ""
    column: KanbanColumn
    created_at: datetime
    updated_at: datetime
    # When the card was moved into ``done`` by a tool call. Optional;
    # surfaces in the UI as a "completed at" timestamp.
    completed_at: datetime | None = None
    # The session that last touched the card via a tool call (if any).
    # Lets the UI link "this card was finished by session 01HJ...".
    last_touched_by_session_id: str | None = None
    # Optional ordering hint within a column. Lower = closer to top.
    # When unset (``None``), the card sorts by ``created_at`` desc.
    order: int | None = None


class KanbanBoard(_Strict):
    """All cards for one project. Columns are derived from card.column,
    not stored separately, so adding a column means changing the
    ``KanbanColumn`` literal in this module — single source of truth.
    """

    schema_version: int = 1
    cards: list[KanbanCard] = Field(default_factory=list)

    def cards_by_column(self) -> dict[KanbanColumn, list[KanbanCard]]:
        """Group cards by column. Each list ordered by (order, created_at)."""
        out: dict[KanbanColumn, list[KanbanCard]] = {c: [] for c in DEFAULT_COLUMNS}
        for card in self.cards:
            out[card.column].append(card)
        for col in out.values():
            col.sort(
                key=lambda c: (
                    c.order if c.order is not None else 1_000_000,
                    c.created_at,
                ),
            )
        return out

    def find(self, card_id: str) -> KanbanCard | None:
        for c in self.cards:
            if c.id == card_id:
                return c
        return None


class Project(_Strict):
    """One project. ``kanban`` lives in a sibling file on disk
    (``kanban.json``) but the API serialises it inline for convenience.
    """

    schema_version: int = 1
    slug: str
    name: str
    description: str = ""
    root_path: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def new(
        cls,
        *,
        slug: str,
        name: str,
        description: str = "",
        root_path: str | None = None,
    ) -> Project:
        now = datetime.now(UTC)
        return cls(
            slug=slug,
            name=name,
            description=description,
            root_path=root_path,
            created_at=now,
            updated_at=now,
        )
