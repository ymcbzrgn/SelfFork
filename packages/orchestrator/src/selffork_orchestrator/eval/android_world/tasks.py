"""AndroidWorld task definitions — scaffold subset.

Each task is a small data class describing:
- ``name``: stable kebab-case id
- ``description``: operator-facing English description
- ``preconditions``: shell + tool calls to set the device into the
  start state (often a no-op for hello-world tasks)
- ``success_check``: tool calls + an assertion that determines whether
  the autonomous loop finished the task

Faz 1 ships 5 tasks; M7 prep will widen to AndroidWorld's full 116.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "TASK_REGISTRY",
    "AndroidWorldTask",
    "list_tasks",
]


@dataclass(frozen=True, slots=True)
class AndroidWorldTask:
    """One AndroidWorld scaffold task."""

    name: str
    description: str
    app_package: str | None = None
    preconditions: tuple[str, ...] = ()
    success_check: Callable[[dict[str, Any]], bool] | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


def _check_text_visible(needle: str) -> Callable[[dict[str, Any]], bool]:
    needle_lower = needle.lower()

    def _check(snapshot: dict[str, Any]) -> bool:
        text = (snapshot.get("ax_tree") or "").lower()
        return needle_lower in text

    return _check


def _check_app_in_foreground(package: str) -> Callable[[dict[str, Any]], bool]:
    def _check(snapshot: dict[str, Any]) -> bool:
        return snapshot.get("foreground_app") == package

    return _check


TASK_REGISTRY: dict[str, AndroidWorldTask] = {
    "settings_open": AndroidWorldTask(
        name="settings_open",
        description="Open the Android Settings app.",
        app_package="com.android.settings",
        preconditions=("android.intent.action.MAIN",),
        success_check=_check_app_in_foreground("com.android.settings"),
        tags=("happy-path", "lifecycle"),
    ),
    "clock_alarm_create": AndroidWorldTask(
        name="clock_alarm_create",
        description="Open Clock and tap the FAB to create a new alarm at 9:41am.",
        app_package="com.google.android.deskclock",
        preconditions=(),
        success_check=_check_text_visible("9:41"),
        tags=("happy-path", "interaction"),
    ),
    "browser_navigate_to_url": AndroidWorldTask(
        name="browser_navigate_to_url",
        description="Open Chrome and navigate to https://selffork.dev",
        app_package="com.android.chrome",
        preconditions=(),
        success_check=_check_text_visible("selffork.dev"),
        tags=("happy-path", "deeplink"),
    ),
    "contacts_search_name": AndroidWorldTask(
        name="contacts_search_name",
        description="Open Contacts and search for 'Yamac'.",
        app_package="com.google.android.contacts",
        preconditions=(),
        success_check=_check_text_visible("Yamac"),
        tags=("happy-path", "search"),
    ),
    "expo_dev_smoke": AndroidWorldTask(
        name="expo_dev_smoke",
        description="Verify the Expo dev menu can be opened via shake gesture.",
        app_package=None,
        preconditions=(),
        success_check=_check_text_visible("Reload"),
        tags=("happy-path", "expo"),
    ),
}


def list_tasks(tag: str | None = None) -> list[AndroidWorldTask]:
    """Return tasks matching ``tag`` (or every task when ``tag is None``)."""
    if tag is None:
        return list(TASK_REGISTRY.values())
    return [t for t in TASK_REGISTRY.values() if tag in t.tags]
