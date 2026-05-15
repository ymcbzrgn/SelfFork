"""provider_router REST surface — list / sign_in_start / refresh / disconnect."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.provider_router import (
    ProviderRegistry,
    build_provider_router,
)


@pytest.fixture()
def registry() -> ProviderRegistry:
    return ProviderRegistry()


@pytest.fixture()
def client(registry: ProviderRegistry) -> TestClient:
    app = FastAPI()
    app.include_router(build_provider_router(registry=registry))
    return TestClient(app)


def test_list_providers_returns_five(client: TestClient) -> None:
    response = client.get("/api/providers")
    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body}
    assert names == {"claude_pro", "codex", "gemini", "opencode", "mmx"}
    for item in body:
        assert item["status"] == "disconnected"


def test_sign_in_start_returns_session_id(client: TestClient) -> None:
    response = client.post("/api/providers/codex/sign_in_start")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "codex"
    assert len(body["session_id"]) >= 16


def test_sign_in_start_unknown_provider_404(client: TestClient) -> None:
    response = client.post("/api/providers/nope/sign_in_start")
    assert response.status_code == 404


def test_refresh_unknown_provider_404(client: TestClient) -> None:
    assert client.post("/api/providers/nope/refresh").status_code == 404


def test_refresh_known_returns_202(client: TestClient) -> None:
    response = client.post("/api/providers/codex/refresh")
    assert response.status_code == 202


def test_disconnect_marks_status(client: TestClient, registry: ProviderRegistry) -> None:
    record = registry.mark_signed_in("codex", storage_state_path="/tmp/codex.json")
    assert record.status == "connected"
    response = client.post("/api/providers/codex/disconnect")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disconnected"
    assert body["storage_state_path"] is None


def test_disconnect_unknown_provider_404(client: TestClient) -> None:
    assert client.post("/api/providers/nope/disconnect").status_code == 404
