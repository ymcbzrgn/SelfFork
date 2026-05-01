"""ProjectStore — filesystem-backed CRUD for :class:`Project` + :class:`KanbanBoard`.

Layout per ``project_project_model.md``::

    <root>/<slug>/
    ├── project.json    # Project meta
    ├── kanban.json     # KanbanBoard state
    ├── audit/          # session audit logs (created on first run)
    ├── workspaces/     # sandbox dirs (created on first run)
    └── sessions/       # plan snapshots, last-round-text records (future)

Writes are atomic via ``tempfile.mkstemp`` + ``os.replace``. Concurrent
processes are NOT supported — the store assumes a single dashboard /
CLI invocation at a time. The orchestrator is single-tenant.

Read errors on a single project's files don't blow up the listing —
malformed files are logged and skipped, preserving the rest of the
listing for the dashboard.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from selffork_orchestrator.projects.model import (
    DEFAULT_COLUMNS,
    KanbanBoard,
    KanbanCard,
    KanbanColumn,
    Project,
    make_card_id,
)
from selffork_orchestrator.projects.slug import normalize_slug, validate_slug
from selffork_shared.errors import ConfigError, SelfForkError
from selffork_shared.logging import get_logger

__all__ = ["ProjectStore"]

_log = get_logger(__name__)

_PROJECT_FILE = "project.json"
_KANBAN_FILE = "kanban.json"


# Sentinel for "field omitted, leave the value alone" vs "explicit None
# = clear the value". Defined before the class because method default
# values are evaluated at class-body time.
class _Sentinel:
    pass


_SENTINEL = _Sentinel()


class ProjectStore:
    """Thin wrapper around the project-dir layout."""

    def __init__(self, *, root: Path) -> None:
        self._root = root.expanduser()

    @property
    def root(self) -> Path:
        return self._root

    # ── CRUD: Project ─────────────────────────────────────────────────

    def create(
        self,
        *,
        name: str,
        description: str = "",
        root_path: str | None = None,
        slug: str | None = None,
    ) -> Project:
        """Create a new project on disk. Raises if the slug is taken."""
        chosen_slug = slug if slug is not None else normalize_slug(name)
        validate_slug(chosen_slug)

        target = self._project_dir(chosen_slug)
        if target.exists():
            raise ConfigError(
                f"project slug {chosen_slug!r} already exists at {target}",
            )

        project = Project.new(
            slug=chosen_slug,
            name=name,
            description=description,
            root_path=root_path,
        )
        target.mkdir(parents=True, exist_ok=False)
        # audit + workspaces + sessions sub-dirs created lazily by their
        # first writers; we only seed the project meta + an empty board.
        self._save_project(project)
        self._save_board(chosen_slug, KanbanBoard())
        _log.info("project_created", slug=chosen_slug, name=name)
        return project

    def load(self, slug: str) -> Project | None:
        """Return the project, or ``None`` if its directory is missing."""
        validate_slug(slug)
        path = self._project_dir(slug) / _PROJECT_FILE
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SelfForkError(
                f"project.json malformed at {path}: {exc}",
            ) from exc
        return Project.model_validate(data)

    def list_all(self) -> list[Project]:
        """List every project on disk, sorted by slug. Skips malformed."""
        if not self._root.is_dir():
            return []
        out: list[Project] = []
        for entry in sorted(self._root.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            try:
                validate_slug(entry.name)
            except ConfigError:
                continue
            try:
                project = self.load(entry.name)
            except SelfForkError as exc:
                _log.warning(
                    "project_skip_malformed",
                    slug=entry.name,
                    reason=str(exc),
                )
                continue
            if project is not None:
                out.append(project)
        return out

    def update_meta(
        self,
        slug: str,
        *,
        name: str | None = None,
        description: str | None = None,
        root_path: str | None | _Sentinel = _SENTINEL,
    ) -> Project:
        """Patch a project's mutable metadata. Touches updated_at."""
        validate_slug(slug)
        project = self.load(slug)
        if project is None:
            raise ConfigError(f"project {slug!r} not found")
        updated = project.model_copy(
            update={
                **({"name": name} if name is not None else {}),
                **({"description": description} if description is not None else {}),
                **({"root_path": root_path} if not isinstance(root_path, _Sentinel) else {}),
                "updated_at": datetime.now(UTC),
            },
        )
        self._save_project(updated)
        return updated

    def delete(self, slug: str) -> bool:
        """Remove a project's metadata files. Returns True if removed.

        Audit + workspace dirs are NOT touched — they may still be
        referenced from the global audit dir or active workspaces. We
        leave that cleanup to the caller (CLI: ``selffork project rm
        --hard <slug>`` is a future surgery).
        """
        validate_slug(slug)
        target = self._project_dir(slug)
        if not target.is_dir():
            return False
        for filename in (_PROJECT_FILE, _KANBAN_FILE):
            with contextlib.suppress(FileNotFoundError):
                (target / filename).unlink()
        # Only rmdir if empty so we don't nuke audit / workspaces.
        with contextlib.suppress(OSError):
            target.rmdir()
        return True

    # ── CRUD: Kanban ──────────────────────────────────────────────────

    def load_board(self, slug: str) -> KanbanBoard:
        """Return the board. Empty board for projects without a kanban file."""
        validate_slug(slug)
        path = self._kanban_path(slug)
        if not path.is_file():
            return KanbanBoard()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SelfForkError(
                f"kanban.json malformed at {path}: {exc}",
            ) from exc
        return KanbanBoard.model_validate(data)

    def save_board(self, slug: str, board: KanbanBoard) -> None:
        validate_slug(slug)
        self._save_board(slug, board)

    def add_card(
        self,
        slug: str,
        *,
        title: str,
        body: str = "",
        column: KanbanColumn = "backlog",
        order: int | None = None,
    ) -> KanbanCard:
        """Append a new card. Returns the card with its minted id."""
        validate_slug(slug)
        if column not in DEFAULT_COLUMNS:
            raise ConfigError(f"invalid column {column!r}")
        if not title.strip():
            raise ConfigError("card title cannot be empty")
        board = self.load_board(slug)
        now = datetime.now(UTC)
        card = KanbanCard(
            id=make_card_id(),
            title=title,
            body=body,
            column=column,
            created_at=now,
            updated_at=now,
            order=order,
        )
        board.cards.append(card)
        self._save_board(slug, board)
        return card

    def move_card(
        self,
        slug: str,
        card_id: str,
        *,
        to_column: KanbanColumn,
        touched_by_session_id: str | None = None,
    ) -> KanbanCard:
        """Move a card between columns. ``done`` stamps ``completed_at``."""
        validate_slug(slug)
        if to_column not in DEFAULT_COLUMNS:
            raise ConfigError(f"invalid column {to_column!r}")
        board = self.load_board(slug)
        card = board.find(card_id)
        if card is None:
            raise ConfigError(f"card {card_id!r} not found in project {slug!r}")
        now = datetime.now(UTC)
        updated = card.model_copy(
            update={
                "column": to_column,
                "updated_at": now,
                "completed_at": now if to_column == "done" else None,
                "last_touched_by_session_id": touched_by_session_id
                or card.last_touched_by_session_id,
            },
        )
        board.cards = [updated if c.id == card_id else c for c in board.cards]
        self._save_board(slug, board)
        return updated

    def update_card(
        self,
        slug: str,
        card_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        order: int | None | _Sentinel = _SENTINEL,
    ) -> KanbanCard:
        """Patch a card's mutable fields (title / body / order)."""
        validate_slug(slug)
        board = self.load_board(slug)
        card = board.find(card_id)
        if card is None:
            raise ConfigError(f"card {card_id!r} not found in project {slug!r}")
        update_kwargs: dict[str, object] = {"updated_at": datetime.now(UTC)}
        if title is not None:
            if not title.strip():
                raise ConfigError("card title cannot be empty")
            update_kwargs["title"] = title
        if body is not None:
            update_kwargs["body"] = body
        if not isinstance(order, _Sentinel):
            update_kwargs["order"] = order
        updated = card.model_copy(update=update_kwargs)
        board.cards = [updated if c.id == card_id else c for c in board.cards]
        self._save_board(slug, board)
        return updated

    def delete_card(self, slug: str, card_id: str) -> bool:
        validate_slug(slug)
        board = self.load_board(slug)
        before = len(board.cards)
        board.cards = [c for c in board.cards if c.id != card_id]
        if len(board.cards) == before:
            return False
        self._save_board(slug, board)
        return True

    # ── Layout helpers ────────────────────────────────────────────────

    def project_dir(self, slug: str) -> Path:
        """Public accessor for the per-project root directory."""
        validate_slug(slug)
        return self._project_dir(slug)

    def audit_dir(self, slug: str) -> Path:
        """Per-project audit directory. Created on demand."""
        return self.project_dir(slug) / "audit"

    def workspace_root(self, slug: str) -> Path:
        return self.project_dir(slug) / "workspaces"

    # ── Internals ─────────────────────────────────────────────────────

    def _project_dir(self, slug: str) -> Path:
        return self._root / slug

    def _kanban_path(self, slug: str) -> Path:
        return self._project_dir(slug) / _KANBAN_FILE

    def _project_path(self, slug: str) -> Path:
        return self._project_dir(slug) / _PROJECT_FILE

    def _save_project(self, project: Project) -> None:
        target = self._project_path(project.slug)
        self._atomic_write_json(
            target,
            json.loads(project.model_dump_json()),
        )

    def _save_board(self, slug: str, board: KanbanBoard) -> None:
        target = self._kanban_path(slug)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write_json(
            target,
            json.loads(board.model_dump_json()),
        )

    @staticmethod
    def _atomic_write_json(target: Path, data: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp_name, target)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise
