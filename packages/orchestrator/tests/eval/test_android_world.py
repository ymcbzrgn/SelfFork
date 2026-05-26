"""AndroidWorld scaffold harness — task registry + runner contract."""

from __future__ import annotations

import asyncio

from selffork_orchestrator.eval.android_world import (
    TASK_REGISTRY,
    AndroidWorldRunner,
    AndroidWorldTask,
    list_tasks,
)


def test_task_registry_has_scaffold_tasks() -> None:
    assert len(TASK_REGISTRY) == 5
    assert set(TASK_REGISTRY) == {
        "settings_open",
        "clock_alarm_create",
        "browser_navigate_to_url",
        "contacts_search_name",
        "expo_dev_smoke",
    }


def test_list_tasks_returns_all_when_tag_none() -> None:
    assert len(list_tasks()) == 5


def test_list_tasks_filters_by_tag() -> None:
    happy = list_tasks(tag="happy-path")
    assert len(happy) == 5


def test_list_tasks_unknown_tag_returns_empty() -> None:
    assert list_tasks(tag="zzz-unknown") == []


def test_task_has_required_fields() -> None:
    for name, task in TASK_REGISTRY.items():
        assert task.name == name
        assert task.description
        assert task.success_check is not None


async def test_runner_passes_on_matching_snapshot() -> None:
    task = TASK_REGISTRY["clock_alarm_create"]

    async def executor(_task: AndroidWorldTask) -> dict[str, str]:
        return {"ax_tree": "Alarm set for 9:41am"}

    runner = AndroidWorldRunner(executor)
    outcome = await runner.run_one(task)
    assert outcome.succeeded is True


async def test_runner_fails_on_mismatched_snapshot() -> None:
    task = TASK_REGISTRY["clock_alarm_create"]

    async def executor(_task: AndroidWorldTask) -> dict[str, str]:
        return {"ax_tree": "Empty home screen"}

    runner = AndroidWorldRunner(executor)
    outcome = await runner.run_one(task)
    assert outcome.succeeded is False


async def test_runner_timeout_is_scored_failure() -> None:
    task = TASK_REGISTRY["settings_open"]

    async def slow_executor(_task: AndroidWorldTask) -> dict[str, str]:
        await asyncio.sleep(5.0)
        return {}

    runner = AndroidWorldRunner(slow_executor, timeout_seconds=0.05)
    outcome = await runner.run_one(task)
    assert outcome.succeeded is False
    assert outcome.error == "timeout"


async def test_runner_exception_is_scored_failure() -> None:
    task = TASK_REGISTRY["settings_open"]

    async def crashing_executor(_task: AndroidWorldTask) -> dict[str, str]:
        raise RuntimeError("driver disconnected")

    runner = AndroidWorldRunner(crashing_executor)
    outcome = await runner.run_one(task)
    assert outcome.succeeded is False
    assert outcome.error is not None
    assert "driver disconnected" in outcome.error


async def test_runner_run_all_default_uses_full_registry() -> None:
    async def executor(_task: AndroidWorldTask) -> dict[str, str]:
        return {
            "foreground_app": "com.android.settings",
            "ax_tree": "9:41 selffork.dev Yamac Reload",
        }

    runner = AndroidWorldRunner(executor)
    result = await runner.run_all()
    assert result.total == 5


async def test_run_result_report_shape() -> None:
    async def executor(_task: AndroidWorldTask) -> dict[str, str]:
        return {
            "foreground_app": "com.android.settings",
            "ax_tree": "9:41 selffork.dev Yamac Reload",
        }

    runner = AndroidWorldRunner(executor)
    result = await runner.run_all()
    report = result.as_report()
    assert {"total", "passed", "pass_rate", "outcomes"} <= report.keys()
    assert report["total"] == 5
    assert isinstance(report["pass_rate"], float)


async def test_settings_open_check_uses_foreground_app() -> None:
    task = TASK_REGISTRY["settings_open"]

    async def executor(_task: AndroidWorldTask) -> dict[str, str]:
        return {"foreground_app": "com.android.settings"}

    runner = AndroidWorldRunner(executor)
    outcome = await runner.run_one(task)
    assert outcome.succeeded is True


async def test_settings_open_misses_wrong_app() -> None:
    task = TASK_REGISTRY["settings_open"]

    async def executor(_task: AndroidWorldTask) -> dict[str, str]:
        return {"foreground_app": "com.android.chrome"}

    runner = AndroidWorldRunner(executor)
    outcome = await runner.run_one(task)
    assert outcome.succeeded is False
