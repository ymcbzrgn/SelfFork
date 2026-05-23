"""Tests for :mod:`selffork_orchestrator.dashboard.settings_router`."""

from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.settings import (
    CodexBarUserConfig,
    ModelEndpointConfig,
    YamlSettingsStore,
)
from selffork_orchestrator.dashboard.settings_router import build_settings_router


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip ``SELFFORK_*`` env vars so tests are deterministic."""
    for key in (
        "SELFFORK_VISION__MLX_MODEL_ID",
        "SELFFORK_VISION__MLX_SERVER_URL",
        "SELFFORK_VISION__OLLAMA_MODEL_TAG",
        "SELFFORK_VISION__OLLAMA_HOST",
        "SELFFORK_VISION__AUTO_DETECT",
        "SELFFORK_DESTRUCTIVE_WHITELIST_PATH",
    ):
        monkeypatch.delenv(key, raising=False)


def _build_writable(cfg_path: Path) -> TestClient:
    app = FastAPI()
    app.include_router(build_settings_router(config_path=cfg_path))
    return TestClient(app)


def _build_readonly() -> TestClient:
    app = FastAPI()
    app.include_router(build_settings_router(config_path=None))
    return TestClient(app)


def _build_with_s4_stores(
    tmp_path: Path,
) -> tuple[
    TestClient,
    YamlSettingsStore[ModelEndpointConfig],
    YamlSettingsStore[CodexBarUserConfig],
    Path,
]:
    """Build a router pinned to per-test stores under ``tmp_path``."""
    me_store: YamlSettingsStore[ModelEndpointConfig] = YamlSettingsStore(
        path=tmp_path / "model-endpoint.yaml",
        schema=ModelEndpointConfig,
        default_factory=ModelEndpointConfig,
    )
    cx_store: YamlSettingsStore[CodexBarUserConfig] = YamlSettingsStore(
        path=tmp_path / "codexbar.yaml",
        schema=CodexBarUserConfig,
        default_factory=CodexBarUserConfig,
    )
    dw_override = tmp_path / "destructive-whitelist.yaml"
    app = FastAPI()
    app.include_router(
        build_settings_router(
            config_path=tmp_path / "selffork.yaml",
            model_endpoint_store=me_store,
            codexbar_user_store=cx_store,
            destructive_override_path=dw_override,
        ),
    )
    return TestClient(app), me_store, cx_store, dw_override


def test_get_vision_returns_defaults(tmp_path: Path) -> None:
    client = _build_writable(tmp_path / "selffork.yaml")
    r = client.get("/api/settings/vision")
    assert r.status_code == 200
    data = r.json()
    assert data["mlx_model_id"] == "mlx-community/gemma-4-E2B-it-4bit"
    assert data["mlx_server_url"] == "http://127.0.0.1:8080"
    assert data["ollama_model_tag"] == "gemma4:e2b-q4_K_M"
    assert data["ollama_host"] == "http://127.0.0.1:11434"
    assert data["auto_detect"] is True


def test_post_vision_partial_update_persists(tmp_path: Path) -> None:
    cfg_path = tmp_path / "selffork.yaml"
    client = _build_writable(cfg_path)
    r = client.post(
        "/api/settings/vision",
        json={"mlx_model_id": "custom-org/custom-gemma"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["mlx_model_id"] == "custom-org/custom-gemma"
    # Untouched fields keep defaults
    assert data["ollama_model_tag"] == "gemma4:e2b-q4_K_M"

    # YAML persisted; reload to confirm round-trip
    assert cfg_path.is_file()
    on_disk = yaml.safe_load(cfg_path.read_text())
    assert on_disk["vision"]["mlx_model_id"] == "custom-org/custom-gemma"

    follow_up = client.get("/api/settings/vision")
    assert follow_up.json()["mlx_model_id"] == "custom-org/custom-gemma"


def test_post_vision_503_when_readonly() -> None:
    client = _build_readonly()
    r = client.post("/api/settings/vision", json={"mlx_model_id": "x"})
    assert r.status_code == 503


def test_post_vision_rejects_unknown_field(tmp_path: Path) -> None:
    client = _build_writable(tmp_path / "selffork.yaml")
    # VisionConfigUpdate uses default pydantic strictness; unknown fields
    # are silently dropped by BaseModel (not forbidden). Document that
    # behavior so we notice if we tighten it later.
    r = client.post(
        "/api/settings/vision",
        json={"made_up_field": "noop"},
    )
    assert r.status_code == 200
    # Nothing actually changed
    assert r.json()["mlx_model_id"] == "mlx-community/gemma-4-E2B-it-4bit"


def test_detect_returns_structured_shape_even_when_servers_down(
    tmp_path: Path,
) -> None:
    client = _build_writable(tmp_path / "selffork.yaml")
    r = client.post("/api/settings/vision/detect")
    assert r.status_code == 200
    data = r.json()
    # Neither real server runs during tests
    assert data["mlx_available"] is False
    assert data["ollama_available"] is False
    assert isinstance(data["mlx_error"], str) and data["mlx_error"]
    assert isinstance(data["ollama_error"], str) and data["ollama_error"]
    assert data["mlx_models"] == []
    assert data["ollama_models"] == []


def test_post_vision_preserves_other_yaml_sections(tmp_path: Path) -> None:
    cfg_path = tmp_path / "selffork.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {"runtime": {"backend": "mlx-server"}, "audit": {"enabled": True}},
        ),
    )
    client = _build_writable(cfg_path)
    r = client.post(
        "/api/settings/vision",
        json={"mlx_model_id": "swapped"},
    )
    assert r.status_code == 200
    on_disk = yaml.safe_load(cfg_path.read_text())
    # Vision written
    assert on_disk["vision"]["mlx_model_id"] == "swapped"
    # Other sections untouched
    assert on_disk["runtime"]["backend"] == "mlx-server"
    assert on_disk["audit"]["enabled"] is True


# ── S4 — Model endpoint persistence ─────────────────────────────────────────


def test_get_model_endpoint_returns_defaults_when_absent(tmp_path: Path) -> None:
    client, _me, _cx, _dw = _build_with_s4_stores(tmp_path)
    r = client.get("/api/settings/model-endpoint")
    assert r.status_code == 200
    data = r.json()
    assert data["url"] == "http://127.0.0.1:8080"
    assert data["protocol"] == "openai"
    assert data["model_name"] == "gemma-4-e2b-it"
    assert data["auth_kind"] == "none"
    assert data["auth_secret"] == ""
    assert data["training_endpoint"] == ""


def test_put_model_endpoint_persists_and_round_trips(tmp_path: Path) -> None:
    client, me_store, _cx, _dw = _build_with_s4_stores(tmp_path)
    payload = {
        "url": "http://192.168.1.10:8080",
        "protocol": "mlx",
        "model_name": "gemma-4-26b-a4b-it-4bit",
        "auth_kind": "api-key",
        "auth_secret": "sk-test-123",
        "training_endpoint": "https://train.gpu.example.com",
    }
    r = client.put("/api/settings/model-endpoint", json=payload)
    assert r.status_code == 200
    assert r.json() == payload

    assert me_store.path.is_file()
    on_disk = yaml.safe_load(me_store.path.read_text())
    assert on_disk == payload

    again = client.get("/api/settings/model-endpoint")
    assert again.json() == payload


def test_put_model_endpoint_rejects_unknown_field(tmp_path: Path) -> None:
    client, _me, _cx, _dw = _build_with_s4_stores(tmp_path)
    r = client.put(
        "/api/settings/model-endpoint",
        json={
            "url": "http://1.2.3.4",
            "protocol": "openai",
            "model_name": "gemma",
            "auth_kind": "none",
            "auth_secret": "",
            "training_endpoint": "",
            "extra": "should fail",
        },
    )
    assert r.status_code == 422


def test_test_model_endpoint_returns_health_for_unreachable(
    tmp_path: Path,
) -> None:
    """No real server runs — health probe surfaces transport error."""
    client, _me, _cx, _dw = _build_with_s4_stores(tmp_path)
    r = client.post(
        "/api/settings/model-endpoint/test",
        json={
            "url": "http://127.0.0.1:59999",  # closed port
            "protocol": "openai",
            "model_name": "test",
            "auth_kind": "none",
            "auth_secret": "",
            "training_endpoint": "",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["status_code"] is None
    assert isinstance(body["latency_ms"], int)
    assert body.get("detail")


def test_test_model_endpoint_uses_persisted_when_no_payload(
    tmp_path: Path,
) -> None:
    """Empty body falls back to the persisted config."""
    client, me_store, _cx, _dw = _build_with_s4_stores(tmp_path)
    me_store.write(
        ModelEndpointConfig(
            url="http://127.0.0.1:59998",
            protocol="openai",
            model_name="test",
            auth_kind="none",
            auth_secret="",
            training_endpoint="",
        )
    )
    r = client.post("/api/settings/model-endpoint/test")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["status_code"] is None


# ── S4 — Destructive whitelist persistence ──────────────────────────────────


def test_get_destructive_whitelist_returns_default_when_no_override(
    tmp_path: Path,
) -> None:
    client, _me, _cx, _dw = _build_with_s4_stores(tmp_path)
    r = client.get("/api/settings/destructive-whitelist")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "default"
    # 7 categories ship in the bundled YAML
    assert {c["id"] for c in body["categories"]} == {
        "prod_deploy",
        "db_destructive",
        "force_push",
        "file_destructive",
        "account_destructive",
        "financial",
        "social_outbound",
    }
    # raw_yaml is the bundled file body, not empty
    assert "destructive_actions:" in body["raw_yaml"]


def test_put_destructive_whitelist_persists_and_flips_source(
    tmp_path: Path,
) -> None:
    client, _me, _cx, dw_override = _build_with_s4_stores(tmp_path)
    new_yaml = (
        "destructive_actions:\n"
        "  - id: prod_deploy\n"
        "    description: 'Test override - production deploy only'\n"
        "    confirm_window_hours: 12\n"
        "    match_any:\n"
        "      - tool: git\n"
        "        args_contains: ['push', 'origin', 'main']\n"
    )
    r = client.put(
        "/api/settings/destructive-whitelist",
        json={"yaml_body": new_yaml},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "override"
    assert len(body["categories"]) == 1
    assert body["categories"][0]["id"] == "prod_deploy"
    assert body["categories"][0]["confirm_window_hours"] == 12
    assert dw_override.is_file()


def test_put_destructive_whitelist_rejects_invalid_yaml(tmp_path: Path) -> None:
    client, _me, _cx, _dw = _build_with_s4_stores(tmp_path)
    r = client.put(
        "/api/settings/destructive-whitelist",
        json={"yaml_body": "this:\n  is: : broken"},
    )
    assert r.status_code == 400
    assert "invalid YAML" in r.json()["detail"]


def test_put_destructive_whitelist_rejects_invalid_schema(
    tmp_path: Path,
) -> None:
    client, _me, _cx, _dw = _build_with_s4_stores(tmp_path)
    # Missing required ``id`` key inside a category.
    r = client.put(
        "/api/settings/destructive-whitelist",
        json={
            "yaml_body": (
                "destructive_actions:\n"
                "  - description: no id\n"
                "    confirm_window_hours: 4\n"
                "    match_any: []\n"
            )
        },
    )
    assert r.status_code == 400
    assert "invalid whitelist schema" in r.json()["detail"]


def test_put_destructive_category_window_updates_single_field(
    tmp_path: Path,
) -> None:
    client, _me, _cx, dw_override = _build_with_s4_stores(tmp_path)
    r = client.put(
        "/api/settings/destructive-whitelist/social_outbound/window",
        json={"confirm_window_hours": 8},
    )
    assert r.status_code == 200
    body = r.json()
    # Source flipped to override + window updated
    assert body["source"] == "override"
    target = next(
        c for c in body["categories"] if c["id"] == "social_outbound"
    )
    assert target["confirm_window_hours"] == 8
    # Other categories preserved their bundled defaults
    prod = next(c for c in body["categories"] if c["id"] == "prod_deploy")
    assert prod["confirm_window_hours"] == 4
    # File created on disk
    assert dw_override.is_file()


def test_put_destructive_category_window_404_unknown_category(
    tmp_path: Path,
) -> None:
    client, _me, _cx, _dw = _build_with_s4_stores(tmp_path)
    r = client.put(
        "/api/settings/destructive-whitelist/nope/window",
        json={"confirm_window_hours": 6},
    )
    assert r.status_code == 404


def test_put_destructive_category_window_validates_range(
    tmp_path: Path,
) -> None:
    client, _me, _cx, _dw = _build_with_s4_stores(tmp_path)
    r = client.put(
        "/api/settings/destructive-whitelist/prod_deploy/window",
        json={"confirm_window_hours": 0},
    )
    assert r.status_code == 422


# ── S4 — CodexBar user knobs ─────────────────────────────────────────────────


def test_get_codexbar_settings_returns_defaults(tmp_path: Path) -> None:
    client, _me, _cx, _dw = _build_with_s4_stores(tmp_path)
    r = client.get("/api/settings/codexbar")
    assert r.status_code == 200
    data = r.json()
    assert data["version_pin"] == ""
    assert data["auto_update"] is True
    assert data["binary_path_override"] == ""


def test_put_codexbar_settings_persists(tmp_path: Path) -> None:
    client, _me, cx_store, _dw = _build_with_s4_stores(tmp_path)
    payload = {
        "version_pin": "v0.27.0",
        "auto_update": False,
        "binary_path_override": "/usr/local/bin/codexbar",
    }
    r = client.put("/api/settings/codexbar", json=payload)
    assert r.status_code == 200
    assert r.json() == payload
    assert cx_store.path.is_file()
    on_disk = yaml.safe_load(cx_store.path.read_text())
    assert on_disk == payload
    again = client.get("/api/settings/codexbar")
    assert again.json() == payload


def test_put_codexbar_settings_rejects_extra_fields(tmp_path: Path) -> None:
    client, _me, _cx, _dw = _build_with_s4_stores(tmp_path)
    r = client.put(
        "/api/settings/codexbar",
        json={
            "version_pin": "",
            "auto_update": True,
            "binary_path_override": "",
            "rogue": "field",
        },
    )
    assert r.status_code == 422


def test_yaml_settings_store_atomic_write_replaces_tempfile(
    tmp_path: Path,
) -> None:
    """The on-disk file appears via ``replace``; the temp file is gone."""
    client, me_store, _cx, _dw = _build_with_s4_stores(tmp_path)
    payload = {
        "url": "http://atomic-test",
        "protocol": "openai",
        "model_name": "x",
        "auth_kind": "none",
        "auth_secret": "",
        "training_endpoint": "",
    }
    r = client.put("/api/settings/model-endpoint", json=payload)
    assert r.status_code == 200
    # File exists, temp is cleaned up
    assert me_store.path.is_file()
    temp_path = me_store.path.with_suffix(me_store.path.suffix + ".tmp")
    assert not temp_path.exists()


def test_put_destructive_whitelist_refuses_when_env_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """audit-god MINOR #2 regression: PUT must refuse with 409 when
    ``SELFFORK_DESTRUCTIVE_WHITELIST_PATH`` is set, so the operator's
    edits don't get silently shadowed by the env-pinned path."""
    monkeypatch.setenv(
        "SELFFORK_DESTRUCTIVE_WHITELIST_PATH",
        str(tmp_path / "env-pinned.yaml"),
    )
    client, _me, _cx, _dw = _build_with_s4_stores(tmp_path)
    r = client.put(
        "/api/settings/destructive-whitelist",
        json={"yaml_body": "destructive_actions: []\n"},
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "SELFFORK_DESTRUCTIVE_WHITELIST_PATH" in detail


def test_put_destructive_window_refuses_when_env_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """audit-god MINOR #2 regression (per-category variant)."""
    monkeypatch.setenv(
        "SELFFORK_DESTRUCTIVE_WHITELIST_PATH",
        str(tmp_path / "env-pinned.yaml"),
    )
    client, _me, _cx, _dw = _build_with_s4_stores(tmp_path)
    r = client.put(
        "/api/settings/destructive-whitelist/prod_deploy/window",
        json={"confirm_window_hours": 8},
    )
    assert r.status_code == 409
