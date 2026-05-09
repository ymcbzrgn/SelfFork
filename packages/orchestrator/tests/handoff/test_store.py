"""Tests for :class:`HandoffBundleStore`."""
from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from selffork_orchestrator.handoff.bundle import (
    ActiveTask,
    HandoffBundle,
    ToolState,
)
from selffork_orchestrator.handoff.store import (
    HandoffBundleStore,
    default_handoff_root,
)


def _bundle(
    *,
    bundle_id: str = "handoff-1",
    session_id: str = "session-1",
    project_slug: str | None = "demo",
    from_cli: str = "claude-code",
    to_cli: str = "codex",
) -> HandoffBundle:
    return HandoffBundle.model_validate(
        {
            "bundle_id": bundle_id,
            "session_id": session_id,
            "project_slug": project_slug,
            "from_cli": from_cli,
            "to_cli": to_cli,
            "active_task": ActiveTask(title="task"),
            "tool_state": ToolState(cwd="/tmp/work"),
            "created_at": datetime.now(tz=UTC),
        },
    )


def test_default_handoff_root_under_home() -> None:
    assert default_handoff_root() == Path.home() / ".selffork"


def test_save_creates_file_under_project_layout(tmp_path: Path) -> None:
    store = HandoffBundleStore(root=tmp_path)
    bundle = _bundle(bundle_id="handoff-1", project_slug="demo")
    path = store.save(bundle)
    assert path.exists()
    assert path == (
        tmp_path
        / "projects"
        / "demo"
        / "sessions"
        / "session-1"
        / "handoff"
        / "bundle-handoff-1.json"
    )


def test_save_handles_orphan_session(tmp_path: Path) -> None:
    store = HandoffBundleStore(root=tmp_path)
    bundle = _bundle(project_slug=None)
    path = store.save(bundle)
    assert path == (
        tmp_path
        / "sessions"
        / "session-1"
        / "handoff"
        / "bundle-handoff-1.json"
    )


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    store = HandoffBundleStore(root=tmp_path)
    bundle = _bundle()
    store.save(bundle)
    rehydrated = store.load(
        session_id="session-1",
        bundle_id="handoff-1",
        project_slug="demo",
    )
    assert rehydrated == bundle


def test_load_returns_none_when_missing(tmp_path: Path) -> None:
    store = HandoffBundleStore(root=tmp_path)
    assert (
        store.load(session_id="session-x", bundle_id="handoff-x", project_slug="demo")
        is None
    )


def test_load_returns_none_on_invalid_json(tmp_path: Path) -> None:
    store = HandoffBundleStore(root=tmp_path)
    bundle = _bundle()
    path = store.save(bundle)
    path.write_text("{broken json", encoding="utf-8")
    assert (
        store.load(session_id="session-1", bundle_id="handoff-1", project_slug="demo")
        is None
    )


def test_list_for_session_orders_by_mtime(tmp_path: Path) -> None:
    store = HandoffBundleStore(root=tmp_path)
    first = _bundle(bundle_id="handoff-1")
    store.save(first)
    time.sleep(0.01)  # ensure mtime difference
    second = _bundle(bundle_id="handoff-2")
    store.save(second)
    listing = store.list_for_session(session_id="session-1", project_slug="demo")
    assert [b.bundle_id for b in listing] == ["handoff-1", "handoff-2"]


def test_list_for_session_empty_when_dir_missing(tmp_path: Path) -> None:
    store = HandoffBundleStore(root=tmp_path)
    assert store.list_for_session(session_id="x", project_slug="demo") == []


def test_remove_deletes_existing_bundle(tmp_path: Path) -> None:
    store = HandoffBundleStore(root=tmp_path)
    bundle = _bundle()
    path = store.save(bundle)
    assert (
        store.remove(
            session_id="session-1",
            bundle_id="handoff-1",
            project_slug="demo",
        )
        is True
    )
    assert not path.exists()


def test_remove_returns_false_when_missing(tmp_path: Path) -> None:
    store = HandoffBundleStore(root=tmp_path)
    assert (
        store.remove(
            session_id="missing",
            bundle_id="handoff-x",
            project_slug="demo",
        )
        is False
    )


def test_save_skips_other_session_paths(tmp_path: Path) -> None:
    """Saving with project_slug=A doesn't pollute the orphan session path."""
    store = HandoffBundleStore(root=tmp_path)
    a = _bundle(bundle_id="handoff-1", project_slug="a")
    b = _bundle(bundle_id="handoff-2", project_slug=None)
    store.save(a)
    store.save(b)
    project_listing = store.list_for_session(session_id="session-1", project_slug="a")
    orphan_listing = store.list_for_session(session_id="session-1", project_slug=None)
    assert [bd.bundle_id for bd in project_listing] == ["handoff-1"]
    assert [bd.bundle_id for bd in orphan_listing] == ["handoff-2"]
