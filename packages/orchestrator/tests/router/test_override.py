"""CliOverrideStore tests — (cli, model) override, sticky + single-turn (S6)."""

from __future__ import annotations

from pathlib import Path

from selffork_orchestrator.dashboard.settings.store import YamlSettingsStore
from selffork_orchestrator.router.override import (
    CliOverrideStore,
    StickyOverrides,
)


def _store(tmp_path: Path) -> CliOverrideStore:
    yaml_store: YamlSettingsStore[StickyOverrides] = YamlSettingsStore(
        path=tmp_path / "cli_override.yaml",
        schema=StickyOverrides,
        default_factory=StickyOverrides,
    )
    return CliOverrideStore(sticky_store=yaml_store)


def test_sticky_cli_only(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set(workspace="alpha", cli="claude-code", sticky=True)
    peeked = store.peek("alpha")
    assert peeked is not None
    assert peeked.cli == "claude-code"
    assert peeked.model is None
    assert peeked.sticky is True


def test_sticky_cli_and_model(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set(workspace="alpha", cli="codex", model="gpt-5.3-codex", sticky=True)
    peeked = store.peek("alpha")
    assert peeked is not None
    assert peeked.cli == "codex"
    assert peeked.model == "gpt-5.3-codex"


def test_sticky_survives_reopen(tmp_path: Path) -> None:
    _store(tmp_path).set(
        workspace="alpha", cli="codex", model="gpt-5.5", sticky=True
    )
    peeked = _store(tmp_path).peek("alpha")
    assert peeked is not None
    assert peeked.cli == "codex"
    assert peeked.model == "gpt-5.5"


def test_single_turn_consumed_once(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set(workspace="alpha", cli="gemini-cli", sticky=False)
    assert store.peek("alpha") is not None  # peek does not consume
    first = store.get_active("alpha")
    assert first is not None
    assert first.cli == "gemini-cli"
    assert first.sticky is False
    assert store.get_active("alpha") is None  # consumed


def test_single_turn_does_not_persist(tmp_path: Path) -> None:
    _store(tmp_path).set(workspace="alpha", cli="codex", sticky=False)
    assert _store(tmp_path).peek("alpha") is None


def test_single_turn_supersedes_sticky(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set(workspace="alpha", cli="claude-code", model="opus", sticky=True)
    store.set(workspace="alpha", cli="opencode", sticky=False)
    consumed = store.get_active("alpha")
    assert consumed is not None
    assert consumed.cli == "opencode"
    assert consumed.sticky is False
    fallback = store.get_active("alpha")
    assert fallback is not None
    assert fallback.cli == "claude-code"
    assert fallback.model == "opus"
    assert fallback.sticky is True


def test_clear_removes_both(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set(workspace="alpha", cli="codex", model="gpt-5.5", sticky=True)
    store.set(workspace="alpha", cli="opencode", sticky=False)
    assert store.clear("alpha") is True
    assert store.peek("alpha") is None
    assert store.clear("alpha") is False


def test_list_sticky(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set(workspace="a", cli="codex", model="gpt-5.5", sticky=True)
    store.set(workspace="b", cli="claude-code", sticky=True)
    sticky = store.list_sticky()
    assert sticky["a"].cli == "codex"
    assert sticky["a"].model == "gpt-5.5"
    assert sticky["b"].cli == "claude-code"
    assert sticky["b"].model is None


def test_get_active_missing_returns_none(tmp_path: Path) -> None:
    assert _store(tmp_path).get_active("never") is None
