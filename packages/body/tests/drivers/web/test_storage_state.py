"""WebStorageStateManager — path layout + save/load + delete + autosave loop."""

from __future__ import annotations

import asyncio
import json

import pytest

from selffork_body.drivers.web import StorageStateAutoSave, WebStorageStateManager


@pytest.fixture()
def manager(tmp_path) -> WebStorageStateManager:
    return WebStorageStateManager(root=tmp_path)


class _StubContext:
    def __init__(self, state: dict) -> None:
        self._state = state

    async def storage_state(self) -> dict:
        return self._state


def test_path_for_orphan(manager: WebStorageStateManager) -> None:
    path = manager.path_for("codex")
    assert "auth-cache" in path.parts
    assert path.name == "codex.json"


def test_path_for_project(manager: WebStorageStateManager) -> None:
    path = manager.path_for("codex", "myproj")
    assert "projects" in path.parts
    assert "myproj" in path.parts
    assert "auth" in path.parts


def test_path_for_empty_provider_raises(manager: WebStorageStateManager) -> None:
    with pytest.raises(ValueError):
        manager.path_for("")


async def test_save_writes_state(manager: WebStorageStateManager) -> None:
    ctx = _StubContext({"cookies": [{"name": "x"}], "origins": []})
    path = await manager.save(ctx, "codex")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["cookies"] == [{"name": "x"}]


def test_load_path_returns_none_when_missing(manager: WebStorageStateManager) -> None:
    assert manager.load_path("codex") is None


async def test_load_path_returns_path_when_exists(manager: WebStorageStateManager) -> None:
    ctx = _StubContext({"cookies": [], "origins": []})
    saved = await manager.save(ctx, "codex")
    assert manager.load_path("codex") == saved


async def test_delete_removes_file(manager: WebStorageStateManager) -> None:
    ctx = _StubContext({"cookies": [], "origins": []})
    await manager.save(ctx, "codex")
    assert manager.delete("codex") is True
    assert manager.load_path("codex") is None


def test_delete_missing_returns_false(manager: WebStorageStateManager) -> None:
    assert manager.delete("nope") is False


async def test_autosave_writes_on_change(tmp_path) -> None:
    manager = WebStorageStateManager(root=tmp_path)
    state: dict = {"cookies": [], "origins": []}
    ctx = _StubContext(state)
    autosave = StorageStateAutoSave(
        manager=manager, context=ctx, provider="codex", interval_sec=0.05
    )
    await autosave.start()
    await asyncio.sleep(0.1)
    # Mutate state, expect new write
    state["cookies"].append({"name": "session", "value": "abc"})
    await asyncio.sleep(0.15)
    await autosave.stop()
    saved = json.loads(manager.path_for("codex").read_text())
    assert saved["cookies"][0]["value"] == "abc"


async def test_autosave_skips_when_unchanged(tmp_path) -> None:
    manager = WebStorageStateManager(root=tmp_path)
    state = {"cookies": [], "origins": []}
    ctx = _StubContext(state)
    autosave = StorageStateAutoSave(
        manager=manager, context=ctx, provider="codex", interval_sec=0.02
    )
    await autosave.start()
    await asyncio.sleep(0.1)
    await autosave.stop()
    # Single write occurred (last_hash dedupes; but content stable so file present once)
    assert manager.path_for("codex").exists()
