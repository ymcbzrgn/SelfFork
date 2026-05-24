"""CliRuntimeStore tests — Self-Jr-mutable per-CLI effort + models (S6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from selffork_orchestrator.dashboard.settings.store import YamlSettingsStore
from selffork_orchestrator.router.cli_config import (
    CliRuntimeConfig,
    CliRuntimeStore,
)


def _store(tmp_path: Path) -> CliRuntimeStore:
    return CliRuntimeStore(
        store=YamlSettingsStore(
            path=tmp_path / "cli_runtime.yaml",
            schema=CliRuntimeConfig,
            default_factory=CliRuntimeConfig,
        )
    )


def test_effort_seeds_from_capability_default(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.effort_for("claude-code") == "max"  # operator always-max seed
    assert store.effort_for("codex") == "xhigh"
    assert store.effort_for("opencode") is None  # capability default None


def test_set_effort_overrides_seed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_effort(cli="claude-code", effort="low")
    assert store.effort_for("claude-code") == "low"


def test_set_effort_persists(tmp_path: Path) -> None:
    _store(tmp_path).set_effort(cli="codex", effort="minimal")
    assert _store(tmp_path).effort_for("codex") == "minimal"


def test_set_effort_none_clears_to_seed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_effort(cli="claude-code", effort="low")
    store.set_effort(cli="claude-code", effort=None)
    assert store.effort_for("claude-code") == "max"


def test_set_effort_invalid_level_raises(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="does not support effort"):
        store.set_effort(cli="codex", effort="bogus")


def test_set_effort_unknown_cli_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown cli"):
        _store(tmp_path).set_effort(cli="bogus", effort="low")


def test_set_enabled_models(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_enabled_models(cli="codex", models=["gpt-5.5", "gpt-5.4-mini"])
    assert store.enabled_models_for("codex") == ("gpt-5.5", "gpt-5.4-mini")
    assert store.models_override()["codex"] == ("gpt-5.5", "gpt-5.4-mini")


def test_enabled_models_unset_is_all(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.enabled_models_for("codex") is None
    assert store.models_override() == {}


def test_set_enabled_models_clear(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_enabled_models(cli="codex", models=["gpt-5.5"])
    store.set_enabled_models(cli="codex", models=[])
    assert store.enabled_models_for("codex") is None


def test_set_enabled_models_invalid_raises(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="unknown models"):
        store.set_enabled_models(cli="codex", models=["not-a-real-model"])
