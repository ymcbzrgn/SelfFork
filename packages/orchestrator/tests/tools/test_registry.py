"""Unit tests for :class:`ToolRegistry` + the kanban tools."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import Field

from selffork_orchestrator.projects.store import ProjectStore
from selffork_orchestrator.tools.base import (
    ToolArgs,
    ToolCall,
    ToolContext,
    ToolRegistry,
    ToolSpec,
)
from selffork_orchestrator.tools.kanban import (
    KanbanCardAddArgs,
    KanbanCardDoneArgs,
    build_kanban_tools,
)


def _ctx_with_project(tmp_path: Path) -> tuple[ToolContext, ProjectStore]:
    store = ProjectStore(root=tmp_path / "projects")
    store.create(name="Calc")
    ctx = ToolContext(
        session_id="01HJTESTSESSION",
        project_slug="calc",
        project_store=store,
    )
    return ctx, store


def _ctx_orphan(tmp_path: Path) -> ToolContext:
    return ToolContext(
        session_id="01HJTESTSESSION",
        project_slug=None,
        project_store=ProjectStore(root=tmp_path / "projects"),
    )


# ── ToolRegistry mechanics ───────────────────────────────────────────────────


class _SquareArgs(ToolArgs):
    n: int = Field(ge=0)


def _square(_ctx: ToolContext, args: _SquareArgs) -> dict[str, object]:
    return {"result": args.n * args.n}


class TestRegistry:
    def test_register_and_lookup(self) -> None:
        spec = ToolSpec(
            name="square",
            description="square a number",
            args_model=_SquareArgs,
            handler=_square,
        )
        reg = ToolRegistry([spec])
        assert reg.names() == ["square"]
        assert reg.get("square") is spec

    def test_duplicate_name_raises(self) -> None:
        spec = ToolSpec(
            name="dup",
            description="x",
            args_model=_SquareArgs,
            handler=_square,
        )
        reg = ToolRegistry([spec])
        with pytest.raises(ValueError, match="already registered"):
            reg.register(spec)

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(ValueError):
            ToolSpec(
                name="bad name",
                description="x",
                args_model=_SquareArgs,
                handler=_square,
            )

    def test_unknown_tool_returns_unknown_tool_status(self, tmp_path: Path) -> None:
        reg = ToolRegistry()
        result = reg.invoke(
            ToolCall(tool="nonexistent", args={}, order_in_reply=0),
            _ctx_orphan(tmp_path),
        )
        assert result.status == "unknown_tool"

    def test_invalid_args_returns_invalid_args(self, tmp_path: Path) -> None:
        reg = ToolRegistry(
            [
                ToolSpec(
                    name="square",
                    description="x",
                    args_model=_SquareArgs,
                    handler=_square,
                ),
            ],
        )
        # n=-1 violates ge=0.
        result = reg.invoke(
            ToolCall(tool="square", args={"n": -1}, order_in_reply=0),
            _ctx_orphan(tmp_path),
        )
        assert result.status == "invalid_args"

    def test_handler_raises_returns_handler_error(self, tmp_path: Path) -> None:
        def _boom(_ctx: ToolContext, _args: _SquareArgs) -> dict[str, object]:
            raise RuntimeError("explode")

        reg = ToolRegistry(
            [
                ToolSpec(
                    name="boom",
                    description="x",
                    args_model=_SquareArgs,
                    handler=_boom,
                ),
            ],
        )
        result = reg.invoke(
            ToolCall(tool="boom", args={"n": 3}, order_in_reply=0),
            _ctx_orphan(tmp_path),
        )
        assert result.status == "handler_error"
        assert "explode" in (result.error or "")

    def test_ok_payload(self, tmp_path: Path) -> None:
        reg = ToolRegistry(
            [
                ToolSpec(
                    name="square",
                    description="x",
                    args_model=_SquareArgs,
                    handler=_square,
                ),
            ],
        )
        result = reg.invoke(
            ToolCall(tool="square", args={"n": 5}, order_in_reply=0),
            _ctx_orphan(tmp_path),
        )
        assert result.status == "ok"
        assert result.payload == {"result": 25}

    def test_catalog_lists_specs(self) -> None:
        reg = ToolRegistry(
            [
                ToolSpec(
                    name="square",
                    description="square a number",
                    args_model=_SquareArgs,
                    handler=_square,
                ),
            ],
        )
        catalog = reg.catalog()
        assert len(catalog) == 1
        assert catalog[0]["name"] == "square"
        assert "args_schema" in catalog[0]


# ── Kanban tools ─────────────────────────────────────────────────────────────


class TestKanbanCardAdd:
    def test_creates_card_in_default_column(self, tmp_path: Path) -> None:
        ctx, store = _ctx_with_project(tmp_path)
        reg = ToolRegistry(build_kanban_tools())
        result = reg.invoke(
            ToolCall(
                tool="kanban_card_add",
                args={"title": "Build add()"},
                order_in_reply=0,
            ),
            ctx,
        )
        assert result.status == "ok"
        assert result.payload is not None
        assert result.payload["column"] == "backlog"
        # Card actually appears in the persisted board.
        board = store.load_board("calc")
        assert len(board.cards) == 1
        assert board.cards[0].title == "Build add()"

    def test_validates_title_length(self, tmp_path: Path) -> None:
        ctx, _ = _ctx_with_project(tmp_path)
        reg = ToolRegistry(build_kanban_tools())
        result = reg.invoke(
            ToolCall(
                tool="kanban_card_add",
                args={"title": ""},
                order_in_reply=0,
            ),
            ctx,
        )
        assert result.status == "invalid_args"

    def test_orphan_session_unauthorized(self, tmp_path: Path) -> None:
        ctx = _ctx_orphan(tmp_path)
        reg = ToolRegistry(build_kanban_tools())
        result = reg.invoke(
            ToolCall(
                tool="kanban_card_add",
                args={"title": "anything"},
                order_in_reply=0,
            ),
            ctx,
        )
        assert result.status == "unauthorized"


class TestKanbanCardMoveAndDone:
    def test_move_then_done(self, tmp_path: Path) -> None:
        ctx, store = _ctx_with_project(tmp_path)
        reg = ToolRegistry(build_kanban_tools())
        # Seed a card by hand.
        card = store.add_card("calc", title="X")

        moved = reg.invoke(
            ToolCall(
                tool="kanban_card_move",
                args={"card_id": card.id, "to_column": "in_progress"},
                order_in_reply=0,
            ),
            ctx,
        )
        assert moved.status == "ok"
        assert moved.payload is not None
        assert moved.payload["to_column"] == "in_progress"

        done = reg.invoke(
            ToolCall(
                tool="kanban_card_done",
                args={"card_id": card.id},
                order_in_reply=0,
            ),
            ctx,
        )
        assert done.status == "ok"
        assert done.payload is not None
        assert done.payload["to_column"] == "done"
        assert done.payload["completed_at"] is not None

        # Persisted state matches.
        board = store.load_board("calc")
        assert board.cards[0].column == "done"
        assert board.cards[0].last_touched_by_session_id == "01HJTESTSESSION"


class TestKanbanCardUpdate:
    def test_patches_title_and_body(self, tmp_path: Path) -> None:
        ctx, store = _ctx_with_project(tmp_path)
        reg = ToolRegistry(build_kanban_tools())
        card = store.add_card("calc", title="old", body="old body")
        result = reg.invoke(
            ToolCall(
                tool="kanban_card_update",
                args={"card_id": card.id, "title": "new", "body": "new body"},
                order_in_reply=0,
            ),
            ctx,
        )
        assert result.status == "ok"
        loaded = store.load_board("calc").find(card.id)
        assert loaded is not None
        assert loaded.title == "new"
        assert loaded.body == "new body"


class TestArgsModelDefaults:
    """Regression guards for the args models themselves."""

    def test_card_add_default_column_is_backlog(self) -> None:
        args = KanbanCardAddArgs(title="x")
        assert args.column == "backlog"

    def test_card_done_requires_id(self) -> None:
        from pydantic import ValidationError

        # Pydantic raises when the required ``card_id`` field is missing.
        with pytest.raises(ValidationError):
            KanbanCardDoneArgs()  # type: ignore[call-arg]
