"""Tests for :mod:`selffork_orchestrator.dashboard.heartbeat_wire` (F-AG #3).

The dashboard process owns these callable factories; the Heartbeat
executor invokes them when Self Jr decides on ``TASK_START`` or
``KANBAN_SUGGEST``. S4 is the first sprint where they're actually
wired — pre-S4 they returned ``skipped`` outcomes.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from selffork_orchestrator.dashboard.heartbeat_wire import (
    make_kanban_card_creator,
    make_task_starter,
)
from selffork_orchestrator.projects.store import ProjectStore


@pytest.mark.asyncio
async def test_task_starter_writes_prd_and_returns_pid(tmp_path: Path) -> None:
    """A successful spawn lands a PRD file + returns a real pid."""
    true_bin = shutil.which("true") or "/bin/true"
    starter = make_task_starter(
        selffork_script=Path(true_bin),
        projects_root=tmp_path,
    )
    pid = await starter("demo", "## PRD\n\nDo the thing.\n")
    assert isinstance(pid, int)
    assert pid > 0

    # PRD file landed under the project's heartbeat-prds dir
    prd_dir = tmp_path / "demo" / "heartbeat-prds"
    assert prd_dir.is_dir()
    prds = list(prd_dir.glob("*.md"))
    assert len(prds) == 1
    assert "Do the thing." in prds[0].read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_task_starter_returns_none_on_spawn_failure(
    tmp_path: Path,
) -> None:
    """A missing binary surfaces as pid=None (executor → ``failed``)."""
    starter = make_task_starter(
        selffork_script=tmp_path / "no-such-binary",
        projects_root=tmp_path,
    )
    pid = await starter("demo", "irrelevant")
    assert pid is None


@pytest.mark.asyncio
async def test_task_starter_sanitises_project_slug(tmp_path: Path) -> None:
    """Slashes / spaces in slug don't escape the projects_root sandbox."""
    true_bin = shutil.which("true") or "/bin/true"
    starter = make_task_starter(
        selffork_script=Path(true_bin),
        projects_root=tmp_path,
    )
    pid = await starter("../escape/slash", "x")
    assert pid is not None
    # The escape attempt is sanitised; nothing landed outside tmp_path.
    assert not (tmp_path.parent / "escape").exists()
    # ``..`` keeps its dot chars but ``/`` collapses to ``-`` so the
    # final filename is one regular directory under tmp_path.
    sanitised = tmp_path / "..-escape-slash" / "heartbeat-prds"
    assert sanitised.is_dir()


@pytest.mark.asyncio
async def test_kanban_card_creator_adds_real_card(tmp_path: Path) -> None:
    """The creator routes through ProjectStore and returns the card id."""
    store = ProjectStore(root=tmp_path)
    store.create(name="Test", description="t", slug="test-proj")

    creator = make_kanban_card_creator(projects_root=tmp_path)
    card_id = await creator(
        "test-proj", "From Self Jr", "Heartbeat says: ship it."
    )
    assert isinstance(card_id, str) and card_id

    # Roundtrip via the store to confirm persistence
    board = store.load_board("test-proj")
    match = next(
        (card for card in board.cards if card.id == card_id), None
    )
    assert match is not None
    assert match.title == "From Self Jr"
    assert "ship it" in match.body


@pytest.mark.asyncio
async def test_kanban_card_creator_propagates_invalid_input(
    tmp_path: Path,
) -> None:
    """Garbage slugs / empty titles surface as exceptions to the executor
    (which translates to ``outcome='failed'`` in the audit log)."""
    store = ProjectStore(root=tmp_path)
    store.create(name="OK", description="", slug="ok-proj")
    creator = make_kanban_card_creator(projects_root=tmp_path)
    # Empty title is rejected by add_card -> ConfigError; the
    # executor catches the exception and emits ``failed``.
    with pytest.raises(Exception):  # noqa: B017
        await creator("ok-proj", "", "body")


@pytest.mark.asyncio
async def test_build_default_heartbeat_accepts_callables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``build_default_heartbeat`` plumbs the F-AG #3 callables through
    to the executor."""
    from selffork_orchestrator.heartbeat.config import (
        build_default_heartbeat,
    )

    # Force a clean env — disable the daemon so we don't touch the
    # network and so AutonomyStore.default() returns no persisted file.
    for key in (
        "SELFFORK_HEARTBEAT_ENABLED",
        "SELFFORK_TALK_MODEL_ENDPOINT",
        "SELFFORK_TALK_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    # Redirect the autonomy YAML to tmp_path so no operator file leaks in.
    monkeypatch.setenv(
        "HOME", str(tmp_path)
    )  # AutonomyStore.default() expands ``~``.

    captured_bridge = object()

    async def _starter(project: str, prd: str) -> int | None:
        return 42

    async def _creator(project: str, title: str, body: str) -> str:
        return "card-fake"

    scheduler = build_default_heartbeat(
        telegram_bridge=captured_bridge,
        task_starter=_starter,
        kanban_card_creator=_creator,
    )
    executor = scheduler._executor
    assert executor is not None
    assert executor._telegram is captured_bridge
    assert executor._task_starter is _starter
    assert executor._kanban_creator is _creator
