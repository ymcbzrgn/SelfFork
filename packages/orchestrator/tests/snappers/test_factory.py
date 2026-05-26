"""Tests for snapper factory and registry."""
from __future__ import annotations

import pytest

from selffork_orchestrator.snappers import (
    ClaudeSnapper,
    CodexSnapper,
    GeminiSnapper,
    MinimaxSnapper,
    OpenCodeSnapper,
    Snapper,
    ZaiSnapper,
    build_default_snappers,
    build_snapper,
    registered_snapper_ids,
)


def test_registered_snapper_ids_matches_active_default_fleet() -> None:
    """The default fleet excludes via-opencode entries (minimax-cli, zai)."""
    ids = set(registered_snapper_ids())
    assert ids == {
        "claude-code",
        "codex",
        "gemini-cli",
        "opencode",
    }
    assert "minimax-cli" not in ids
    assert "zai" not in ids


def test_build_snapper_returns_correct_class_for_active_fleet() -> None:
    assert isinstance(build_snapper("claude-code"), ClaudeSnapper)
    assert isinstance(build_snapper("codex"), CodexSnapper)
    assert isinstance(build_snapper("gemini-cli"), GeminiSnapper)
    assert isinstance(build_snapper("opencode"), OpenCodeSnapper)


def test_build_snapper_still_constructs_via_opencode_routes() -> None:
    """``minimax-cli`` + ``zai`` remain explicit-construction targets."""
    assert isinstance(build_snapper("minimax-cli"), MinimaxSnapper)
    assert isinstance(build_snapper("zai"), ZaiSnapper)


def test_build_snapper_sets_cli_id() -> None:
    assert build_snapper("claude-code").cli_id == "claude-code"
    assert build_snapper("codex").cli_id == "codex"
    assert build_snapper("gemini-cli").cli_id == "gemini-cli"
    assert build_snapper("opencode").cli_id == "opencode"
    assert build_snapper("minimax-cli").cli_id == "minimax-cli"
    assert build_snapper("zai").cli_id == "zai"


def test_build_snapper_unknown_raises() -> None:
    with pytest.raises(ValueError, match="no snapper for cli agent"):
        build_snapper("nonexistent-cli")


def test_build_default_snappers_returns_one_per_registered_id() -> None:
    snappers = build_default_snappers()
    assert {s.cli_id for s in snappers} == set(registered_snapper_ids())
    assert all(isinstance(s, Snapper) for s in snappers)


def test_build_default_snappers_excludes_via_opencode_routes() -> None:
    """Operator 2026-05-26: minimax + glm via opencode → no standalone snapper."""
    snappers = build_default_snappers()
    cli_ids = {s.cli_id for s in snappers}
    assert "minimax-cli" not in cli_ids
    assert "zai" not in cli_ids
    assert len(snappers) == 4
