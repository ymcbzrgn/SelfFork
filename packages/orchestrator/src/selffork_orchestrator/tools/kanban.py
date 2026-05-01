"""Kanban tool implementations — Jr's first concrete tool surface.

Each tool delegates to the active :class:`ProjectStore` (passed in via
:class:`ToolContext`). Tools that require a project bound to the active
session refuse to run when ``ctx.project_slug is None``.

Args models are deliberately permissive on optional fields so a small
Jr emitting a sparse JSON object still gets its call accepted, but
required fields use Pydantic's strict semantics so a missing ``card_id``
fails ``invalid_args`` rather than a runtime error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field

from selffork_orchestrator.projects.model import KanbanColumn
from selffork_orchestrator.tools.base import (
    ToolArgs,
    ToolContext,
    ToolSpec,
    raise_unauthorized,
)

if TYPE_CHECKING:
    from selffork_orchestrator.projects.store import ProjectStore

__all__ = [
    "KanbanCardAddArgs",
    "KanbanCardDoneArgs",
    "KanbanCardMoveArgs",
    "KanbanCardUpdateArgs",
    "build_kanban_tools",
]


def _store(ctx: ToolContext) -> tuple[ProjectStore, str]:
    """Resolve the active store + slug; refuse when no project."""
    if ctx.project_slug is None:
        raise_unauthorized(
            "this tool requires the active session to belong to a "
            "project; pass --project <slug> when starting `selffork run`",
        )
        # ``raise_unauthorized`` raises; this line is unreachable but
        # appeases type checkers that don't know NoReturn.
        raise AssertionError("unreachable")
    from selffork_orchestrator.projects.store import ProjectStore

    if not isinstance(ctx.project_store, ProjectStore):
        raise TypeError(
            "tool context's project_store is not a ProjectStore instance",
        )
    return ctx.project_store, ctx.project_slug


# ── kanban_card_add ──────────────────────────────────────────────────────────


class KanbanCardAddArgs(ToolArgs):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=4000)
    column: KanbanColumn = "backlog"


def _kanban_card_add(ctx: ToolContext, args: KanbanCardAddArgs) -> dict[str, Any]:
    store, slug = _store(ctx)
    card = store.add_card(
        slug,
        title=args.title,
        body=args.body,
        column=args.column,
    )
    return {
        "card_id": card.id,
        "column": card.column,
        "created_at": card.created_at.isoformat(),
    }


# ── kanban_card_move ─────────────────────────────────────────────────────────


class KanbanCardMoveArgs(ToolArgs):
    card_id: str
    to_column: KanbanColumn


def _kanban_card_move(
    ctx: ToolContext,
    args: KanbanCardMoveArgs,
) -> dict[str, Any]:
    store, slug = _store(ctx)
    card = store.move_card(
        slug,
        args.card_id,
        to_column=args.to_column,
        touched_by_session_id=ctx.session_id,
    )
    return {
        "card_id": card.id,
        "from_column": None,  # we don't track the previous column on the model
        "to_column": card.column,
        "completed_at": card.completed_at.isoformat() if card.completed_at else None,
    }


# ── kanban_card_done ─────────────────────────────────────────────────────────
#
# Convenience wrapper: ``move_card to_column="done"``. We expose it as
# its own tool because Jr asks "is this card done?" much more often
# than "move this card to a specific column", and a more semantic name
# tends to produce more reliable small-model output.


class KanbanCardDoneArgs(ToolArgs):
    card_id: str


def _kanban_card_done(
    ctx: ToolContext,
    args: KanbanCardDoneArgs,
) -> dict[str, Any]:
    store, slug = _store(ctx)
    card = store.move_card(
        slug,
        args.card_id,
        to_column="done",
        touched_by_session_id=ctx.session_id,
    )
    return {
        "card_id": card.id,
        "to_column": card.column,
        "completed_at": card.completed_at.isoformat() if card.completed_at else None,
    }


# ── kanban_card_update ───────────────────────────────────────────────────────


class KanbanCardUpdateArgs(ToolArgs):
    card_id: str
    title: str | None = None
    body: str | None = None


def _kanban_card_update(
    ctx: ToolContext,
    args: KanbanCardUpdateArgs,
) -> dict[str, Any]:
    store, slug = _store(ctx)
    card = store.update_card(
        slug,
        args.card_id,
        title=args.title,
        body=args.body,
    )
    return {
        "card_id": card.id,
        "title": card.title,
        "body": card.body,
        "updated_at": card.updated_at.isoformat(),
    }


# ── Public registry builder ──────────────────────────────────────────────────


def build_kanban_tools() -> list[ToolSpec[Any]]:
    """Return the four kanban tool specs in canonical order.

    Stable order so the catalog injected into Jr's system prompt
    produces the same byte sequence across runs (helps prompt caching
    when we eventually use that).
    """
    return [
        ToolSpec(
            name="kanban_card_add",
            description=(
                "Append a new card to the project's kanban board. Default column is 'backlog'."
            ),
            args_model=KanbanCardAddArgs,
            handler=_kanban_card_add,
        ),
        ToolSpec(
            name="kanban_card_move",
            description=(
                "Move an existing card to a different column "
                "(backlog | in_progress | review | done)."
            ),
            args_model=KanbanCardMoveArgs,
            handler=_kanban_card_move,
        ),
        ToolSpec(
            name="kanban_card_done",
            description=(
                "Mark a card as done. Equivalent to kanban_card_move(card_id, to_column='done')."
            ),
            args_model=KanbanCardDoneArgs,
            handler=_kanban_card_done,
        ),
        ToolSpec(
            name="kanban_card_update",
            description="Patch a card's title and/or body. id is required.",
            args_model=KanbanCardUpdateArgs,
            handler=_kanban_card_update,
        ),
    ]
