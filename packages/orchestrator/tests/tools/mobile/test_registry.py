"""Registry shape — counts + names + defer flags for the Faz 1 mobile fleet."""

from __future__ import annotations

from selffork_orchestrator.tools import build_default_registry
from selffork_orchestrator.tools.mobile import (
    build_android_tools,
    build_crash_state_tools,
    build_expo_tools,
    build_ios_tools,
    build_mobile_tools,
    build_ui_verify_tools,
)


def test_mobile_tools_total_count() -> None:
    """Faz 1 ships ~122 mobile tools (operator lock §9.3)."""
    assert len(build_mobile_tools()) == 122


def test_ios_pack_count() -> None:
    assert len(build_ios_tools()) == 45


def test_android_pack_count() -> None:
    assert len(build_android_tools()) == 45


def test_expo_pack_count() -> None:
    assert len(build_expo_tools()) == 12


def test_ui_verify_pack_count() -> None:
    assert len(build_ui_verify_tools()) == 10


def test_crash_state_pack_count() -> None:
    assert len(build_crash_state_tools()) == 10


def test_mobile_tool_names_unique() -> None:
    names = [t.name for t in build_mobile_tools()]
    assert len(set(names)) == len(names)


def test_mobile_tools_registered_in_default() -> None:
    registry = build_default_registry()
    registered = set(registry.names())
    for spec in build_mobile_tools():
        assert spec.name in registered


def test_ios_top_10_are_eager() -> None:
    expected_eager = {
        "ios_click", "ios_type", "ios_swipe", "ios_press_key",
        "ios_screenshot", "ios_a11y_tree",
        "ios_app_launch", "ios_app_terminate", "ios_list_apps",
        "ios_get_orientation",
    }
    eager = {t.name for t in build_ios_tools() if not t.defer_loading}
    assert expected_eager == eager


def test_android_top_10_are_eager() -> None:
    expected_eager = {
        "android_click", "android_type", "android_swipe", "android_press_key",
        "android_screenshot", "android_a11y_tree",
        "android_app_launch", "android_app_terminate", "android_list_apps",
        "android_get_orientation",
    }
    eager = {t.name for t in build_android_tools() if not t.defer_loading}
    assert expected_eager == eager


def test_ui_verify_all_eager() -> None:
    """UI-verify is always eager — observe loop needs it every cycle."""
    for spec in build_ui_verify_tools():
        assert not spec.defer_loading, f"{spec.name} should be eager"


def test_expo_all_deferred() -> None:
    """Expo is operator dev-time tooling — never in the eager prompt."""
    for spec in build_expo_tools():
        assert spec.defer_loading, f"{spec.name} should be deferred"


def test_crash_state_all_deferred() -> None:
    """Crash/state is on-demand, not part of the agentic mobile loop."""
    for spec in build_crash_state_tools():
        assert spec.defer_loading, f"{spec.name} should be deferred"


def test_eager_deferred_split() -> None:
    """Faz 1 target: 30 eager + 92 deferred = 122 total."""
    tools = build_mobile_tools()
    eager = [t for t in tools if not t.defer_loading]
    deferred = [t for t in tools if t.defer_loading]
    assert len(eager) == 30
    assert len(deferred) == 92


def test_mobile_tool_names_have_platform_prefix() -> None:
    """Every mobile tool starts with ios_/android_/expo_/ui_verify_/crash_."""
    valid_prefixes = ("ios_", "android_", "expo_", "ui_verify_", "crash_")
    for spec in build_mobile_tools():
        assert spec.name.startswith(valid_prefixes), spec.name


def test_default_registry_size_after_faz_1() -> None:
    """Faz 1 contribution: 122 mobile tools (30 eager + 92 deferred).

    Pinned to a lower bound so the test survives Faz 2+ growth — the
    canonical Faz 2 close test asserts the exact total in
    ``tests/tools/browser/test_registry.py``.
    """
    registry = build_default_registry()
    names = registry.names()
    mobile = [n for n in names if n.startswith(("ios_", "android_", "expo_", "ui_verify_", "crash_"))]  # noqa: E501
    assert len(mobile) == 122
    eager_mobile = sum(
        1 for n in mobile if not registry.get(n).defer_loading  # type: ignore[union-attr]
    )
    assert eager_mobile == 30


def test_no_collision_with_existing_body_tools() -> None:
    """body_* tools (Faz 0) must not collide with mobile tools (Faz 1)."""
    registry = build_default_registry()
    names = registry.names()
    body_names = [n for n in names if n.startswith("body_")]
    mobile_names = [
        n for n in names
        if n.startswith(("ios_", "android_", "expo_", "ui_verify_", "crash_"))
    ]
    assert len(body_names) == 10
    assert len(mobile_names) == 122
    # No overlap by construction (prefix-disjoint)
    assert set(body_names).isdisjoint(set(mobile_names))
