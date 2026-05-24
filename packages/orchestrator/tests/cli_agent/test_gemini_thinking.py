"""Tests for GeminiCliAgent thinking settings-write (S6 E2.3).

Opt-in: only when an effort != "dynamic" AND a model is pinned does the
agent write a workspace-local .gemini/settings.json with the (verified)
experimental gate + a model-targeted thinkingConfig override.
"""
from __future__ import annotations

import json
from pathlib import Path

from selffork_orchestrator.cli_agent.gemini_cli import GeminiCliAgent
from selffork_shared.config import CLIAgentConfig


def _agent(*, model: str | None = None, effort: str | None = None) -> GeminiCliAgent:
    return GeminiCliAgent(
        CLIAgentConfig(agent="gemini-cli", model=model, effort=effort),
    )


def _settings_path(ws: Path) -> Path:
    return ws / ".gemini" / "settings.json"


def _thinking(data: dict) -> dict:
    override = data["modelConfigs"]["customOverrides"][0]
    return override["modelConfig"]["generateContentConfig"]["thinkingConfig"]


def test_writes_thinking_budget_for_2_5(tmp_path: Path) -> None:
    _agent(model="gemini-2.5-pro", effort="high").prepare_workspace(str(tmp_path))
    data = json.loads(_settings_path(tmp_path).read_text(encoding="utf-8"))
    assert data["experimental"]["dynamicModelConfiguration"] is True
    overrides = data["modelConfigs"]["customOverrides"]
    assert len(overrides) == 1
    assert overrides[0]["match"]["model"] == "gemini-2.5-pro"
    assert _thinking(data) == {"thinkingBudget": 24576}


def test_noop_when_effort_dynamic(tmp_path: Path) -> None:
    _agent(model="gemini-2.5-pro", effort="dynamic").prepare_workspace(str(tmp_path))
    assert not _settings_path(tmp_path).exists()


def test_noop_when_effort_none(tmp_path: Path) -> None:
    _agent(model="gemini-2.5-pro", effort=None).prepare_workspace(str(tmp_path))
    assert not _settings_path(tmp_path).exists()


def test_noop_when_model_none(tmp_path: Path) -> None:
    _agent(model=None, effort="high").prepare_workspace(str(tmp_path))
    assert not _settings_path(tmp_path).exists()


def test_read_merge_preserves_existing(tmp_path: Path) -> None:
    path = _settings_path(tmp_path)
    path.parent.mkdir(parents=True)
    existing = {"ui": {"theme": "ANSI"}, "experimental": {"memoryManager": True}}
    path.write_text(json.dumps(existing), encoding="utf-8")
    _agent(model="gemini-2.5-flash", effort="low").prepare_workspace(str(tmp_path))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["ui"]["theme"] == "ANSI"  # preserved
    assert data["experimental"]["memoryManager"] is True  # preserved
    assert data["experimental"]["dynamicModelConfiguration"] is True  # added
    assert _thinking(data) == {"thinkingBudget": 2048}


def test_idempotent_no_duplicate_override(tmp_path: Path) -> None:
    agent = _agent(model="gemini-2.5-pro", effort="high")
    agent.prepare_workspace(str(tmp_path))
    agent.prepare_workspace(str(tmp_path))
    data = json.loads(_settings_path(tmp_path).read_text(encoding="utf-8"))
    matching = [
        o
        for o in data["modelConfigs"]["customOverrides"]
        if o["match"]["model"] == "gemini-2.5-pro"
    ]
    assert len(matching) == 1


def test_gemini_3_high_uses_thinking_level(tmp_path: Path) -> None:
    agent = _agent(model="gemini-3-pro-preview", effort="high")
    agent.prepare_workspace(str(tmp_path))
    data = json.loads(_settings_path(tmp_path).read_text(encoding="utf-8"))
    assert _thinking(data) == {"thinkingLevel": "HIGH"}


def test_gemini_3_unverified_level_is_noop(tmp_path: Path) -> None:
    # Only HIGH is locally-verified for thinkingLevel; 'low' must not write.
    _agent(model="gemini-3-pro-preview", effort="low").prepare_workspace(str(tmp_path))
    assert not _settings_path(tmp_path).exists()


def test_unreadable_file_not_clobbered(tmp_path: Path) -> None:
    path = _settings_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{ broken json", encoding="utf-8")
    _agent(model="gemini-2.5-pro", effort="high").prepare_workspace(str(tmp_path))
    assert path.read_text(encoding="utf-8") == "{ broken json"


def test_other_agent_prepare_workspace_is_noop(tmp_path: Path) -> None:
    # The ABC default no-op: a non-gemini agent writes nothing.
    from selffork_orchestrator.cli_agent.factory import build_cli_agent

    agent = build_cli_agent(
        CLIAgentConfig(agent="claude-code", model="opus", effort="high"),
    )
    agent.prepare_workspace(str(tmp_path))
    assert not (tmp_path / ".gemini").exists()
    assert list(tmp_path.iterdir()) == []
