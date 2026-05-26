"""Faz 3 registry shape — counts + names + defer flags."""

from __future__ import annotations

from selffork_orchestrator.tools import (
    build_default_registry,
    build_desktop_tools,
    build_github_tools,
    build_skills_tools,
)


def test_desktop_pack_count() -> None:
    assert len(build_desktop_tools()) == 15


def test_github_pack_count() -> None:
    """GitHub pack ships 16 tools (one over scope target = issue_comment extra)."""
    assert len(build_github_tools()) == 16


def test_skills_pack_count() -> None:
    assert len(build_skills_tools()) == 10


def test_faz3_total_count() -> None:
    """Faz 3 ships ~40 tools (15 desktop + 16 github + 10 skills = 41)."""
    total = len(build_desktop_tools()) + len(build_github_tools()) + len(build_skills_tools())
    assert total == 41


def test_desktop_names_have_prefix() -> None:
    for spec in build_desktop_tools():
        assert spec.name.startswith("desktop_"), spec.name


def test_github_names_have_prefix() -> None:
    for spec in build_github_tools():
        assert spec.name.startswith("github_"), spec.name


def test_skill_names_have_prefix() -> None:
    for spec in build_skills_tools():
        assert spec.name.startswith("skill_"), spec.name


def test_desktop_eager_top_5() -> None:
    expected = {
        "desktop_click", "desktop_type", "desktop_screenshot",
        "desktop_press_key", "desktop_get_active_app",
    }
    eager = {t.name for t in build_desktop_tools() if not t.defer_loading}
    assert expected == eager


def test_github_eager_top_3() -> None:
    """Self-Jr self-commit + status checks are eager."""
    expected = {"github_pr_create", "github_issue_create", "github_issue_list"}
    eager = {t.name for t in build_github_tools() if not t.defer_loading}
    assert expected == eager


def test_skills_all_deferred() -> None:
    for spec in build_skills_tools():
        assert spec.defer_loading, f"{spec.name} should be deferred"


def test_default_registry_includes_faz3_fleet() -> None:
    """Faz 3 contribution: 41 tools (8 eager + 33 deferred).

    Pinned per-prefix rather than total so the test survives Faz 4+ growth.
    """
    registry = build_default_registry()
    names = registry.names()
    faz3 = [n for n in names if n.startswith(("desktop_", "github_", "skill_"))]
    assert len(faz3) == 41
    eager = sum(
        1 for n in faz3 if not registry.get(n).defer_loading  # type: ignore[union-attr]
    )
    assert eager == 8


def test_no_prefix_collision() -> None:
    registry = build_default_registry()
    names = registry.names()
    desktop = {n for n in names if n.startswith("desktop_")}
    github = {n for n in names if n.startswith("github_")}
    skill = {n for n in names if n.startswith("skill_")}
    assert len(desktop) == 15
    assert len(github) == 16
    assert len(skill) == 10
    # Disjoint with mobile / browser / body
    other = {n for n in names if n.startswith(("ios_", "android_", "browser_", "body_"))}
    assert (desktop | github | skill).isdisjoint(other)
