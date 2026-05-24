"""Tests for Self Jr CLI-router control + introspection tools (S6)."""
from __future__ import annotations

from pathlib import Path

from selffork_orchestrator.dashboard.settings.store import YamlSettingsStore
from selffork_orchestrator.router.cli_config import CliRuntimeConfig, CliRuntimeStore
from selffork_orchestrator.router.override import CliOverrideStore, StickyOverrides
from selffork_orchestrator.tools.base import (
    ToolCall,
    ToolContext,
    ToolRegistry,
    ToolResult,
)
from selffork_orchestrator.tools.router import build_router_tools


def _registry() -> ToolRegistry:
    return ToolRegistry(specs=build_router_tools())


def _override_store(tmp_path: Path) -> CliOverrideStore:
    return CliOverrideStore(
        sticky_store=YamlSettingsStore(
            path=tmp_path / "cli_override.yaml",
            schema=StickyOverrides,
            default_factory=StickyOverrides,
        ),
    )


def _runtime_store(tmp_path: Path) -> CliRuntimeStore:
    return CliRuntimeStore(
        store=YamlSettingsStore(
            path=tmp_path / "cli_runtime.yaml",
            schema=CliRuntimeConfig,
            default_factory=CliRuntimeConfig,
        ),
    )


def _ctx(
    *,
    override_store: object | None = None,
    runtime_store: object | None = None,
) -> ToolContext:
    return ToolContext(
        session_id="session-1",
        project_slug="proj",
        project_store=object(),
        cli_override_store=override_store,
        cli_runtime_store=runtime_store,
    )


def _invoke(
    reg: ToolRegistry,
    tool: str,
    args: dict[str, object],
    ctx: ToolContext,
) -> ToolResult:
    return reg.invoke(ToolCall(tool=tool, args=args, order_in_reply=0), ctx)


# ── set_cli_override ───────────────────────────────────────────────────────────


def test_set_cli_override_persists_sticky(tmp_path: Path) -> None:
    store = _override_store(tmp_path)
    result = _invoke(
        _registry(),
        "set_cli_override",
        {"workspace": "w1", "cli": "claude-code", "model": "opus"},
        _ctx(override_store=store),
    )
    assert result.status == "ok"
    payload = result.payload or {}
    assert payload["applied"] is True
    assert payload["cli"] == "claude-code"
    assert payload["model"] == "opus"
    assert payload["sticky"] is True
    # Sticky → a fresh store at the same YAML path sees it (cross-process).
    fresh = _override_store(tmp_path)
    active = fresh.peek("w1")
    assert active is not None
    assert active.cli == "claude-code"
    assert active.model == "opus"
    assert active.sticky is True


def test_set_cli_override_unknown_cli_rejected(tmp_path: Path) -> None:
    result = _invoke(
        _registry(),
        "set_cli_override",
        {"workspace": "w1", "cli": "bogus-cli"},
        _ctx(override_store=_override_store(tmp_path)),
    )
    payload = result.payload or {}
    assert payload["applied"] is False
    assert "unknown cli" in payload["error"]


def test_set_cli_override_unknown_model_rejected(tmp_path: Path) -> None:
    result = _invoke(
        _registry(),
        "set_cli_override",
        {"workspace": "w1", "cli": "claude-code", "model": "gpt-5.5"},
        _ctx(override_store=_override_store(tmp_path)),
    )
    payload = result.payload or {}
    assert payload["applied"] is False
    assert "no model" in payload["error"]


def test_set_cli_override_without_store_is_unauthorized() -> None:
    result = _invoke(
        _registry(),
        "set_cli_override",
        {"workspace": "w1", "cli": "claude-code"},
        _ctx(),  # no stores wired
    )
    assert result.status == "unauthorized"


# ── clear_cli_override ─────────────────────────────────────────────────────────


def test_clear_cli_override(tmp_path: Path) -> None:
    store = _override_store(tmp_path)
    store.set(workspace="w1", cli="codex", sticky=True)
    result = _invoke(
        _registry(),
        "clear_cli_override",
        {"workspace": "w1"},
        _ctx(override_store=store),
    )
    payload = result.payload or {}
    assert payload["cleared"] is True
    assert store.peek("w1") is None


def test_clear_cli_override_nothing_to_clear(tmp_path: Path) -> None:
    result = _invoke(
        _registry(),
        "clear_cli_override",
        {"workspace": "w1"},
        _ctx(override_store=_override_store(tmp_path)),
    )
    payload = result.payload or {}
    assert payload["cleared"] is False


# ── set_cli_effort ─────────────────────────────────────────────────────────────


def test_set_cli_effort_valid(tmp_path: Path) -> None:
    store = _runtime_store(tmp_path)
    result = _invoke(
        _registry(),
        "set_cli_effort",
        {"cli": "claude-code", "effort": "high"},
        _ctx(runtime_store=store),
    )
    payload = result.payload or {}
    assert payload["applied"] is True
    assert store.effort_for("claude-code") == "high"


def test_set_cli_effort_invalid_level_rejected(tmp_path: Path) -> None:
    result = _invoke(
        _registry(),
        "set_cli_effort",
        {"cli": "claude-code", "effort": "bogus"},
        _ctx(runtime_store=_runtime_store(tmp_path)),
    )
    payload = result.payload or {}
    assert payload["applied"] is False
    assert "does not support" in payload["error"]


def test_set_cli_effort_unknown_cli_rejected(tmp_path: Path) -> None:
    result = _invoke(
        _registry(),
        "set_cli_effort",
        {"cli": "nope", "effort": "high"},
        _ctx(runtime_store=_runtime_store(tmp_path)),
    )
    payload = result.payload or {}
    assert payload["applied"] is False
    assert "unknown cli" in payload["error"]


def test_set_cli_effort_without_store_is_unauthorized() -> None:
    result = _invoke(
        _registry(),
        "set_cli_effort",
        {"cli": "claude-code", "effort": "high"},
        _ctx(),
    )
    assert result.status == "unauthorized"


# ── set_cli_models ─────────────────────────────────────────────────────────────


def test_set_cli_models_valid(tmp_path: Path) -> None:
    store = _runtime_store(tmp_path)
    result = _invoke(
        _registry(),
        "set_cli_models",
        {"cli": "claude-code", "models": ["opus", "sonnet"]},
        _ctx(runtime_store=store),
    )
    payload = result.payload or {}
    assert payload["applied"] is True
    assert store.enabled_models_for("claude-code") == ("opus", "sonnet")


def test_set_cli_models_invalid_rejected(tmp_path: Path) -> None:
    result = _invoke(
        _registry(),
        "set_cli_models",
        {"cli": "claude-code", "models": ["nonexistent"]},
        _ctx(runtime_store=_runtime_store(tmp_path)),
    )
    payload = result.payload or {}
    assert payload["applied"] is False
    assert "unknown models" in payload["error"]


# ── reads ──────────────────────────────────────────────────────────────────────


def test_cli_capabilities_lists_menu() -> None:
    result = _invoke(_registry(), "cli_capabilities", {}, _ctx())
    payload = result.payload or {}
    clis = payload["clis"]
    assert "claude-code" in clis
    assert "opus" in clis["claude-code"]["models"]
    assert clis["gemini-cli"]["per_model_quota"] is True
    assert clis["claude-code"]["per_model_quota"] is False


def test_cli_config_reflects_set_values(tmp_path: Path) -> None:
    store = _runtime_store(tmp_path)
    store.set_effort(cli="claude-code", effort="low")
    result = _invoke(_registry(), "cli_config", {}, _ctx(runtime_store=store))
    payload = result.payload or {}
    assert payload["efforts"]["claude-code"] == "low"
    # resolved_efforts falls back to the seed default for unset CLIs.
    assert payload["resolved_efforts"]["codex"] == "xhigh"


def test_cli_config_seed_default_when_unset(tmp_path: Path) -> None:
    result = _invoke(
        _registry(),
        "cli_config",
        {},
        _ctx(runtime_store=_runtime_store(tmp_path)),
    )
    payload = result.payload or {}
    # claude-code seed default is max (operator always-max habit).
    assert payload["resolved_efforts"]["claude-code"] == "max"


def test_cli_override_read(tmp_path: Path) -> None:
    store = _override_store(tmp_path)
    store.set(
        workspace="w1", cli="gemini-cli", model="gemini-2.5-pro", sticky=True
    )
    result = _invoke(
        _registry(),
        "cli_override",
        {"workspace": "w1"},
        _ctx(override_store=store),
    )
    payload = result.payload or {}
    assert payload["override"]["cli"] == "gemini-cli"
    assert payload["override"]["model"] == "gemini-2.5-pro"


def test_cli_override_read_none(tmp_path: Path) -> None:
    result = _invoke(
        _registry(),
        "cli_override",
        {"workspace": "w1"},
        _ctx(override_store=_override_store(tmp_path)),
    )
    payload = result.payload or {}
    assert payload["override"] is None


# ── cli_affinity ───────────────────────────────────────────────────────────────


def test_cli_affinity_available(monkeypatch) -> None:
    fake = {
        "workspace": "w1",
        "chosen_cli": "claude-code",
        "scores": {"claude-code:opus": 0.7},
    }
    monkeypatch.setattr(
        "selffork_orchestrator.router.affinity_snapshot.read_affinity_snapshot",
        lambda workspace, **_: fake,
    )
    result = _invoke(_registry(), "cli_affinity", {"workspace": "w1"}, _ctx())
    payload = result.payload or {}
    assert payload["available"] is True
    assert payload["affinity"]["chosen_cli"] == "claude-code"


def test_cli_affinity_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "selffork_orchestrator.router.affinity_snapshot.read_affinity_snapshot",
        lambda workspace, **_: None,
    )
    result = _invoke(_registry(), "cli_affinity", {"workspace": "w1"}, _ctx())
    payload = result.payload or {}
    assert payload["available"] is False
