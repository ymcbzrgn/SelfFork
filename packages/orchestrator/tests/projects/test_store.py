"""Unit tests for :class:`ProjectStore` — real filesystem CRUD."""

from __future__ import annotations

from pathlib import Path

import pytest

from selffork_orchestrator.projects.model import KanbanBoard, KanbanCard
from selffork_orchestrator.projects.store import ProjectStore
from selffork_shared.errors import ConfigError, SelfForkError


def _store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(root=tmp_path / "projects")


class TestCreate:
    def test_creates_dir_and_files(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        project = store.create(name="Calculator MVP")
        assert project.slug == "calculator-mvp"
        assert project.name == "Calculator MVP"
        # Layout exists on disk.
        proj_dir = store.project_dir("calculator-mvp")
        assert (proj_dir / "project.json").is_file()
        assert (proj_dir / "kanban.json").is_file()

    def test_duplicate_slug_raises(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Foo")
        with pytest.raises(ConfigError, match="already exists"):
            store.create(name="Foo")

    def test_explicit_slug_validated(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        with pytest.raises(ConfigError):
            store.create(name="OK", slug="UPPER")

    def test_optional_root_path_persisted(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        project = store.create(name="Bound", root_path="/tmp/myrepo")  # noqa: S108
        loaded = store.load("bound")
        assert loaded is not None
        assert loaded.root_path == "/tmp/myrepo"  # noqa: S108
        assert project.root_path == loaded.root_path


class TestLoad:
    def test_missing_returns_none(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert store.load("nope") is None

    def test_round_trip_preserves_fields(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(
            name="Trip",
            description="round trip test",
            root_path=str(tmp_path / "binding"),
        )
        loaded = store.load("trip")
        assert loaded is not None
        assert loaded.description == "round trip test"
        assert loaded.root_path == str(tmp_path / "binding")
        assert loaded.created_at == loaded.updated_at  # fresh project

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Broken")
        # Corrupt the project file.
        (store.project_dir("broken") / "project.json").write_text(
            "not json",
            encoding="utf-8",
        )
        with pytest.raises(SelfForkError, match="malformed"):
            store.load("broken")


class TestListAll:
    def test_empty_root(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert store.list_all() == []

    def test_returns_sorted(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Bravo")
        store.create(name="Alpha")
        store.create(name="Charlie")
        slugs = [p.slug for p in store.list_all()]
        assert slugs == ["alpha", "bravo", "charlie"]

    def test_skips_invalid_dirs(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Real")
        # An invalid dir name should be skipped.
        (tmp_path / "projects" / "INVALID").mkdir()
        slugs = [p.slug for p in store.list_all()]
        assert slugs == ["real"]


class TestUpdateMeta:
    def test_patch_name_only(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Old name")
        updated = store.update_meta("old-name", name="Renamed")
        assert updated.name == "Renamed"
        assert updated.updated_at > updated.created_at

    def test_unset_root_path(self, tmp_path: Path) -> None:
        # Passing root_path=None should clear the bind.
        store = _store(tmp_path)
        store.create(name="Bound", root_path="/tmp/r")  # noqa: S108
        updated = store.update_meta("bound", root_path=None)
        assert updated.root_path is None

    def test_omit_root_path_keeps_value(self, tmp_path: Path) -> None:
        # NOT passing root_path should leave it alone (sentinel default).
        store = _store(tmp_path)
        store.create(name="Bound", root_path="/tmp/r")  # noqa: S108
        updated = store.update_meta("bound", description="new desc")
        assert updated.root_path == "/tmp/r"  # noqa: S108
        assert updated.description == "new desc"

    def test_unknown_slug_raises(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        with pytest.raises(ConfigError, match="not found"):
            store.update_meta("nope", name="x")


class TestKanbanCRUD:
    def test_initial_board_is_empty(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Board")
        board = store.load_board("board")
        assert isinstance(board, KanbanBoard)
        assert board.cards == []

    def test_add_card_default_column_is_backlog(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Board")
        card = store.add_card("board", title="Build add()")
        assert card.column == "backlog"
        assert card.id.startswith("card-")
        assert card.completed_at is None

    def test_move_card_to_done_stamps_completed(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Board")
        card = store.add_card("board", title="Done it")
        moved = store.move_card("board", card.id, to_column="done")
        assert moved.column == "done"
        assert moved.completed_at is not None
        # Moving back resets the stamp.
        moved_back = store.move_card("board", card.id, to_column="in_progress")
        assert moved_back.completed_at is None

    def test_move_invalid_column_raises(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Board")
        card = store.add_card("board", title="x")
        with pytest.raises(ConfigError, match="invalid column"):
            store.move_card("board", card.id, to_column="garbage")  # type: ignore[arg-type]

    def test_move_unknown_card_raises(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Board")
        with pytest.raises(ConfigError, match="not found"):
            store.move_card("board", "card-MISSING", to_column="done")

    def test_update_card_patches_fields(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Board")
        card = store.add_card("board", title="Old", body="")
        updated = store.update_card(
            "board",
            card.id,
            title="New",
            body="filled in",
        )
        assert updated.title == "New"
        assert updated.body == "filled in"
        assert updated.updated_at > card.updated_at

    def test_update_card_blank_title_raises(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Board")
        card = store.add_card("board", title="Old")
        with pytest.raises(ConfigError, match="title cannot be empty"):
            store.update_card("board", card.id, title="   ")

    def test_delete_card(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Board")
        card = store.add_card("board", title="Bye")
        assert store.delete_card("board", card.id) is True
        assert store.load_board("board").cards == []
        assert store.delete_card("board", card.id) is False

    def test_grouping_orders_by_order_then_created(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Board")
        a = store.add_card("board", title="A")
        b = store.add_card("board", title="B", order=10)
        c = store.add_card("board", title="C", order=5)
        # Move all to 'in_progress' so we share a column.
        for card_id in (a.id, b.id, c.id):
            store.move_card("board", card_id, to_column="in_progress")
        groups = store.load_board("board").cards_by_column()
        ids = [card.title for card in groups["in_progress"]]
        # C (order=5) before B (order=10) before A (None → bottom).
        assert ids == ["C", "B", "A"]


class TestAtomicity:
    def test_replace_on_save(self, tmp_path: Path) -> None:
        # Verify that saving twice doesn't leave .tmp leftovers and the
        # second save's content wins.
        store = _store(tmp_path)
        store.create(name="Atom")
        # Mutate via update + verify file content + no .tmp residue.
        store.update_meta("atom", description="v1")
        store.update_meta("atom", description="v2")
        proj_dir = store.project_dir("atom")
        residue = [p for p in proj_dir.iterdir() if p.name.startswith(".")]
        assert residue == []
        loaded = store.load("atom")
        assert loaded is not None
        assert loaded.description == "v2"


class TestDelete:
    def test_delete_returns_true(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create(name="Goner")
        assert store.delete("goner") is True
        assert store.load("goner") is None

    def test_delete_missing_returns_false(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert store.delete("never-there") is False

    def test_delete_keeps_audit_dir(self, tmp_path: Path) -> None:
        # If the audit subdir is non-empty, delete leaves it alone so
        # we don't lose history. The project meta files go away.
        store = _store(tmp_path)
        store.create(name="Hist")
        audit_dir = store.audit_dir("hist")
        audit_dir.mkdir(parents=True)
        (audit_dir / "01HJ.jsonl").write_text("{}\n", encoding="utf-8")
        store.delete("hist")
        assert audit_dir.is_dir()
        assert (audit_dir / "01HJ.jsonl").is_file()


class TestKanbanCardModelInvariants:
    """Sanity checks on the model itself; no store needed."""

    def test_find(self, tmp_path: Path) -> None:
        del tmp_path
        board = KanbanBoard()
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        card = KanbanCard(
            id="card-X",
            title="t",
            column="backlog",
            created_at=now,
            updated_at=now,
        )
        board.cards = [card]
        assert board.find("card-X") is card
        assert board.find("missing") is None
