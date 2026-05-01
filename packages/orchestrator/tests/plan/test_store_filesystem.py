"""Unit tests for :class:`FilesystemPlanStore`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from selffork_orchestrator.plan.model import Plan, SubTask, SubTaskState
from selffork_orchestrator.plan.store_filesystem import FilesystemPlanStore
from selffork_shared.config import PlanConfig
from selffork_shared.errors import PlanLoadError, PlanSaveError


def _make_store(
    tmp_path: Path, *, plan_filename: str = ".selffork/plan.json"
) -> FilesystemPlanStore:
    cfg = PlanConfig(backend="filesystem", plan_filename=plan_filename)
    return FilesystemPlanStore(cfg, workspace_path=str(tmp_path))


class TestInit:
    def test_validates_backend(self, tmp_path: Path) -> None:
        cfg = PlanConfig(backend="git")
        with pytest.raises(ValueError, match="filesystem"):
            FilesystemPlanStore(cfg, workspace_path=str(tmp_path))

    def test_plan_path_under_workspace(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path, plan_filename=".selffork/plan.json")
        assert store.plan_path == tmp_path / ".selffork" / "plan.json"


class TestSaveLoad:
    @pytest.mark.asyncio
    async def test_save_then_load_round_trips(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        plan = Plan.new(session_id="sess1", prd_path="/prd.md")
        plan.subtasks = [
            SubTask(id="a", title="Task A"),
            SubTask(id="b", title="Task B", state=SubTaskState.IN_PROGRESS),
        ]
        await store.save(plan)
        loaded = await store.load()
        assert loaded.session_id == "sess1"
        assert len(loaded.subtasks) == 2
        assert loaded.subtasks[1].state == SubTaskState.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path, plan_filename="deep/nested/plan.json")
        plan = Plan.new(session_id="s", prd_path="/p")
        await store.save(plan)
        assert (tmp_path / "deep" / "nested" / "plan.json").is_file()

    @pytest.mark.asyncio
    async def test_save_overwrites_existing(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        plan_a = Plan.new(session_id="A", prd_path="/p")
        await store.save(plan_a)
        plan_b = Plan.new(session_id="B", prd_path="/p")
        await store.save(plan_b)
        loaded = await store.load()
        assert loaded.session_id == "B"

    @pytest.mark.asyncio
    async def test_save_writes_pretty_json(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        plan = Plan.new(session_id="s", prd_path="/p")
        await store.save(plan)
        text = store.plan_path.read_text(encoding="utf-8")
        # Pretty-printed (indented) and sorted keys
        assert "\n" in text
        parsed = json.loads(text)
        assert parsed["session_id"] == "s"

    @pytest.mark.asyncio
    async def test_load_missing_raises(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        with pytest.raises(PlanLoadError, match="not found"):
            await store.load()

    @pytest.mark.asyncio
    async def test_load_invalid_json_raises(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.plan_path.parent.mkdir(parents=True, exist_ok=True)
        store.plan_path.write_text("{not json", encoding="utf-8")
        with pytest.raises(PlanLoadError, match="JSON"):
            await store.load()

    @pytest.mark.asyncio
    async def test_load_schema_violation_raises(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.plan_path.parent.mkdir(parents=True, exist_ok=True)
        # Missing required ``session_id`` field
        store.plan_path.write_text('{"prd_path": "/p"}', encoding="utf-8")
        with pytest.raises(PlanLoadError, match="schema"):
            await store.load()

    @pytest.mark.asyncio
    async def test_save_to_unwriteable_parent_raises(self, tmp_path: Path) -> None:
        # Make the workspace_root a regular file (not a dir) — mkdir will fail.
        weird = tmp_path / "regular-file"
        weird.write_text("not a dir", encoding="utf-8")
        cfg = PlanConfig(backend="filesystem", plan_filename="plan.json")
        store = FilesystemPlanStore(cfg, workspace_path=str(weird))
        plan = Plan.new(session_id="s", prd_path="/p")
        with pytest.raises(PlanSaveError):
            await store.save(plan)


class TestUpdateSubtaskState:
    @pytest.mark.asyncio
    async def test_transition_persists(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        plan = Plan.new(session_id="s", prd_path="/p")
        plan.subtasks = [SubTask(id="a", title="A")]
        await store.save(plan)
        updated = await store.update_subtask_state("a", SubTaskState.DONE, notes="ok")
        assert updated.subtasks[0].state == SubTaskState.DONE
        assert updated.subtasks[0].notes == "ok"
        # Reload to confirm persisted.
        reloaded = await store.load()
        assert reloaded.subtasks[0].state == SubTaskState.DONE
        assert reloaded.subtasks[0].updated_at is not None

    @pytest.mark.asyncio
    async def test_unknown_subtask_raises(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        plan = Plan.new(session_id="s", prd_path="/p")
        await store.save(plan)
        with pytest.raises(PlanLoadError, match="not in plan"):
            await store.update_subtask_state("nope", SubTaskState.DONE)

    @pytest.mark.asyncio
    async def test_updates_plan_timestamp(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        plan = Plan.new(session_id="s", prd_path="/p")
        plan.subtasks = [SubTask(id="a", title="A")]
        await store.save(plan)
        before = (await store.load()).updated_at
        updated = await store.update_subtask_state("a", SubTaskState.IN_PROGRESS)
        assert updated.updated_at >= before
