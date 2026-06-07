"""Faz 4 VR registry shape — counts + names + defer flags."""

from __future__ import annotations

from selffork_orchestrator.tools import (
    build_default_registry,
    build_vr_tools,
)
from selffork_orchestrator.tools.vr import (
    build_quest_tools,
    build_visionpro_tools,
)


def test_quest_pack_count() -> None:
    assert len(build_quest_tools()) == 19


def test_visionpro_pack_count() -> None:
    assert len(build_visionpro_tools()) == 8


def test_vr_total_count() -> None:
    assert len(build_vr_tools()) == 27


def test_quest_names_have_prefix() -> None:
    for spec in build_quest_tools():
        assert spec.name.startswith("quest_"), spec.name


def test_visionpro_names_have_prefix() -> None:
    for spec in build_visionpro_tools():
        assert spec.name.startswith("visionpro_"), spec.name


def test_quest_eager_top_3() -> None:
    expected = {"quest_screenshot", "quest_app_launch", "quest_recenter"}
    eager = {t.name for t in build_quest_tools() if not t.defer_loading}
    assert expected == eager


def test_visionpro_all_deferred() -> None:
    for spec in build_visionpro_tools():
        assert spec.defer_loading, f"{spec.name} should be deferred"


def test_vr_tools_registered_in_default() -> None:
    registry = build_default_registry()
    names = set(registry.names())
    for spec in build_vr_tools():
        assert spec.name in names


def test_vr_no_collision() -> None:
    registry = build_default_registry()
    names = registry.names()
    quest = {n for n in names if n.startswith("quest_")}
    visionpro = {n for n in names if n.startswith("visionpro_")}
    assert len(quest) == 19
    assert len(visionpro) == 8
    other = {
        n
        for n in names
        if n.startswith(
            (
                "ios_",
                "android_",
                "browser_",
                "desktop_",
                "github_",
                "skill_",
            )
        )
    }
    assert (quest | visionpro).isdisjoint(other)


def test_default_registry_includes_vr_fleet() -> None:
    """Faz 4 contribution: 27 VR tools (3 eager + 24 deferred)."""
    registry = build_default_registry()
    names = registry.names()
    vr = [n for n in names if n.startswith(("quest_", "visionpro_"))]
    assert len(vr) == 27
    eager = sum(
        1
        for n in vr
        if not registry.get(n).defer_loading  # type: ignore[union-attr]
    )
    assert eager == 3
