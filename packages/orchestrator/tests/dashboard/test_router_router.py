"""CLI router API tests — override + affinity + capabilities + config (S6)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.router_router import build_router_router
from selffork_orchestrator.dashboard.settings.store import YamlSettingsStore
from selffork_orchestrator.router import (
    CliAffinityProvider,
    CliOverrideStore,
    CLIRouter,
    CliRuntimeConfig,
    CliRuntimeStore,
    StickyOverrides,
)

_CANDIDATES = ("claude-code", "codex", "gemini-cli")


def _client(tmp_path: Path) -> TestClient:
    router = CLIRouter(
        affinity=CliAffinityProvider(home=tmp_path),
        override_store=CliOverrideStore(
            sticky_store=YamlSettingsStore(
                path=tmp_path / "override.yaml",
                schema=StickyOverrides,
                default_factory=StickyOverrides,
            )
        ),
        runtime_store=CliRuntimeStore(
            store=YamlSettingsStore(
                path=tmp_path / "runtime.yaml",
                schema=CliRuntimeConfig,
                default_factory=CliRuntimeConfig,
            )
        ),
        candidates=_CANDIDATES,
    )
    app = FastAPI()
    app.include_router(build_router_router(router=router))
    return TestClient(app)


def test_override_cli_model_crud(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        resp = client.post(
            "/api/router/override",
            json={
                "workspace": "alpha",
                "cli": "codex",
                "model": "gpt-5.3-codex",
                "sticky": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["cli"] == "codex"
        assert body["model"] == "gpt-5.3-codex"
        got = client.get("/api/router/override/alpha").json()
        assert got["cli"] == "codex"
        assert got["model"] == "gpt-5.3-codex"
        assert client.delete("/api/router/override/alpha").json() == {
            "cleared": True
        }
        assert client.get("/api/router/override/alpha").json() is None


def test_override_cli_only(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        resp = client.post(
            "/api/router/override",
            json={"workspace": "alpha", "cli": "claude-code"},
        )
        assert resp.status_code == 200
        assert resp.json()["model"] is None
        assert resp.json()["sticky"] is True


def test_override_unknown_cli_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        resp = client.post(
            "/api/router/override",
            json={"workspace": "a", "cli": "bogus", "sticky": True},
        )
        assert resp.status_code == 400
        assert "unknown cli" in resp.json()["detail"]


def test_override_unknown_model_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        resp = client.post(
            "/api/router/override",
            json={"workspace": "a", "cli": "codex", "model": "nope-9999"},
        )
        assert resp.status_code == 400
        assert "unknown model" in resp.json()["detail"]


def test_affinity_view_lists_pairs_and_efforts(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.get("/api/router/affinity/alpha?task_type=refactor").json()
        assert body["workspace"] == "alpha"
        assert body["active_override"] is None
        pairs = {(c["cli"], c["model"]) for c in body["candidates"]}
        assert ("claude-code", "opus") in pairs
        assert ("gemini-cli", "gemini-2.5-pro") in pairs
        # cold-start prior everywhere
        assert all(c["score"] == 0.5 for c in body["candidates"])
        # resolved efforts include the seeds
        assert body["efforts"]["claude-code"] == "max"
        assert body["efforts"]["codex"] == "xhigh"


def test_capabilities_endpoint(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        caps = {c["cli"]: c for c in client.get("/api/router/capabilities").json()}
        assert "max" in caps["claude-code"]["effort_levels"]
        assert caps["gemini-cli"]["per_model_quota"] is True
        assert caps["codex"]["per_model_quota"] is False
        assert "gpt-5.5" in caps["codex"]["models"]


def test_config_effort_roundtrip(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        resp = client.put(
            "/api/router/config/effort",
            json={"cli": "claude-code", "effort": "low"},
        )
        assert resp.status_code == 200
        assert resp.json()["efforts"]["claude-code"] == "low"
        assert client.get("/api/router/config").json()["efforts"][
            "claude-code"
        ] == "low"


def test_config_effort_invalid_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        resp = client.put(
            "/api/router/config/effort",
            json={"cli": "codex", "effort": "bogus"},
        )
        assert resp.status_code == 400


def test_config_models_roundtrip(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        resp = client.put(
            "/api/router/config/models",
            json={"cli": "codex", "models": ["gpt-5.5", "gpt-5.4-mini"]},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled_models"]["codex"] == [
            "gpt-5.5",
            "gpt-5.4-mini",
        ]


def test_config_models_invalid_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        resp = client.put(
            "/api/router/config/models",
            json={"cli": "codex", "models": ["nope-9999"]},
        )
        assert resp.status_code == 400
