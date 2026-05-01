"""Unit tests for :mod:`selffork_orchestrator.plan.model`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from selffork_orchestrator.plan.model import Plan, SubTask, SubTaskState


class TestSubTask:
    def test_minimal_construction(self) -> None:
        st = SubTask(id="s1", title="Build API")
        assert st.id == "s1"
        assert st.title == "Build API"
        assert st.description == ""
        assert st.expected_outcome == ""
        assert st.state == SubTaskState.TODO
        assert st.notes == ""
        assert st.updated_at is None

    def test_state_default(self) -> None:
        st = SubTask(id="s1", title="x")
        assert st.state is SubTaskState.TODO

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SubTask(id="s1", title="x", bogus_field="oops")  # type: ignore[call-arg]

    def test_state_literal_values(self) -> None:
        for value in ["todo", "in_progress", "done", "abandoned"]:
            st = SubTask(id="s", title="t", state=value)  # type: ignore[arg-type]
            assert st.state.value == value


class TestPlan:
    def test_new_sets_timestamps(self) -> None:
        before = datetime.now(UTC)
        plan = Plan.new(session_id="sess1", prd_path="/p.md")
        after = datetime.now(UTC)
        assert before <= plan.created_at <= after
        assert plan.created_at == plan.updated_at
        assert plan.session_id == "sess1"
        assert plan.prd_path == "/p.md"
        assert plan.subtasks == []

    def test_new_with_subtasks(self) -> None:
        subs = [SubTask(id="a", title="A"), SubTask(id="b", title="B")]
        plan = Plan.new(session_id="s", prd_path="/p", subtasks=subs)
        assert len(plan.subtasks) == 2
        assert plan.subtasks[0].id == "a"

    def test_extra_field_rejected(self) -> None:
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            Plan(  # type: ignore[call-arg]
                session_id="s",
                prd_path="/p",
                created_at=now,
                updated_at=now,
                bogus="x",
            )

    def test_find_subtask_hit(self) -> None:
        plan = Plan.new(session_id="s", prd_path="/p")
        plan.subtasks = [SubTask(id="a", title="A"), SubTask(id="b", title="B")]
        assert plan.find_subtask("b") is plan.subtasks[1]

    def test_find_subtask_miss(self) -> None:
        plan = Plan.new(session_id="s", prd_path="/p")
        assert plan.find_subtask("nope") is None

    def test_serialize_round_trip(self) -> None:
        plan = Plan.new(session_id="s", prd_path="/p")
        plan.subtasks.append(
            SubTask(
                id="a",
                title="A",
                description="d",
                expected_outcome="e",
                state=SubTaskState.IN_PROGRESS,
                notes="n",
                updated_at=plan.created_at + timedelta(seconds=5),
            ),
        )
        dumped = plan.model_dump(mode="json")
        rebuilt = Plan.model_validate(dumped)
        assert rebuilt.subtasks[0].state == SubTaskState.IN_PROGRESS
        assert rebuilt.created_at == plan.created_at
