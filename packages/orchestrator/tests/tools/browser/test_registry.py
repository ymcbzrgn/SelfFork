"""Browser registry shape — counts + names + defer flags."""

from __future__ import annotations

from selffork_orchestrator.tools import build_default_registry
from selffork_orchestrator.tools.browser import (
    build_browser_cloak_tools,
    build_browser_device_tools,
    build_browser_intelligent_tools,
    build_browser_interaction_tools,
    build_browser_navigation_tools,
    build_browser_network_tools,
    build_browser_observation_tools,
    build_browser_storage_tools,
    build_browser_tabs_tools,
    build_browser_tools,
)


def test_browser_tools_total_count() -> None:
    """Faz 2 ships ~60 browser tools per scope lock (close to target)."""
    assert len(build_browser_tools()) == 63


def test_browser_pack_counts() -> None:
    assert len(build_browser_interaction_tools()) == 11
    assert len(build_browser_navigation_tools()) == 9
    assert len(build_browser_observation_tools()) == 11
    assert len(build_browser_tabs_tools()) == 6
    assert len(build_browser_storage_tools()) == 6
    assert len(build_browser_intelligent_tools()) == 5
    assert len(build_browser_cloak_tools()) == 5
    assert len(build_browser_network_tools()) == 5
    assert len(build_browser_device_tools()) == 5


def test_browser_tool_names_unique() -> None:
    names = [t.name for t in build_browser_tools()]
    assert len(set(names)) == len(names)


def test_browser_tool_names_have_prefix() -> None:
    for spec in build_browser_tools():
        assert spec.name.startswith("browser_")


def test_browser_eager_bucket() -> None:
    """Top-of-loop tools are eager (always in Self Jr's prompt)."""
    eager = {t.name for t in build_browser_tools() if not t.defer_loading}
    expected = {
        "browser_click",
        "browser_type",
        "browser_press_key",
        "browser_navigate",
        "browser_get_url",
        "browser_wait_for_load_state",
        "browser_screenshot",
        "browser_dom_snapshot",
        "browser_text_content",
        "browser_evaluate",
    }
    assert expected == eager


def test_browser_eager_deferred_split() -> None:
    """Faz 2 target: 10 eager + 53 deferred = 63 total."""
    tools = build_browser_tools()
    eager = [t for t in tools if not t.defer_loading]
    deferred = [t for t in tools if t.defer_loading]
    assert len(eager) == 10
    assert len(deferred) == 53


def test_browser_tools_registered_in_default() -> None:
    registry = build_default_registry()
    names = set(registry.names())
    for spec in build_browser_tools():
        assert spec.name in names


def test_default_registry_includes_browser_fleet() -> None:
    """Faz 2 contribution: 63 browser tools (10 eager + 53 deferred).

    Pinned per-prefix rather than total so the test survives Faz 3+ growth.
    """
    registry = build_default_registry()
    names = registry.names()
    browser = [n for n in names if n.startswith("browser_")]
    assert len(browser) == 63
    eager_browser = sum(
        1 for n in browser if not registry.get(n).defer_loading  # type: ignore[union-attr]
    )
    assert eager_browser == 10


def test_no_browser_mobile_collision() -> None:
    """browser_* and ios_*/android_* must never collide."""
    registry = build_default_registry()
    browser = {n for n in registry.names() if n.startswith("browser_")}
    mobile = {
        n for n in registry.names()
        if n.startswith(("ios_", "android_", "expo_", "ui_verify_", "crash_"))
    }
    assert len(browser) == 63
    assert len(mobile) == 122
    assert browser.isdisjoint(mobile)
