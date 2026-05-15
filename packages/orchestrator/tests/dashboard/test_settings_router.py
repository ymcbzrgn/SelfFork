"""Tests for :mod:`selffork_orchestrator.dashboard.settings_router`."""

from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.settings_router import build_settings_router


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip ``SELFFORK_VISION__*`` env vars so tests are deterministic."""
    for key in (
        "SELFFORK_VISION__MLX_MODEL_ID",
        "SELFFORK_VISION__MLX_SERVER_URL",
        "SELFFORK_VISION__OLLAMA_MODEL_TAG",
        "SELFFORK_VISION__OLLAMA_HOST",
        "SELFFORK_VISION__AUTO_DETECT",
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
