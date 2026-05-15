"""fleet_router REST surface — register / heartbeat / state / list / revoke."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.fleet_router import (
    FleetRegistry,
    build_fleet_router,
)


@pytest.fixture()
def registry() -> FleetRegistry:
    return FleetRegistry(online_grace_sec=60)


@pytest.fixture()
def client(registry: FleetRegistry) -> TestClient:
    app = FastAPI()
    app.include_router(build_fleet_router(registry=registry))
    return TestClient(app)


def test_register_returns_auth_key(client: TestClient) -> None:
    response = client.post(
        "/api/fleet/register",
        json={
            "machine_id": "work-ubuntu",
            "hostname": "work-ubuntu.local",
            "location_tier": "work",
            "version": "0.5.0",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert "auth_key" in body
    assert len(body["auth_key"]) >= 32


def test_register_rejects_duplicate(client: TestClient) -> None:
    payload = {
        "machine_id": "work-ubuntu",
        "hostname": "work-ubuntu.local",
        "location_tier": "work",
        "version": "0.5.0",
    }
    client.post("/api/fleet/register", json=payload)
    response = client.post("/api/fleet/register", json=payload)
    assert response.status_code == 409


def test_heartbeat_unknown_machine_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/fleet/heartbeat",
        json={
            "machine_id": "nope",
            "location_tier": "auto",
            "version": "0.0.0-dev",
        },
    )
    assert response.status_code == 404


def test_heartbeat_marks_online(client: TestClient, registry: FleetRegistry) -> None:
    client.post(
        "/api/fleet/register",
        json={"machine_id": "m", "hostname": "h", "location_tier": "home", "version": "0.5.0"},
    )
    response = client.post(
        "/api/fleet/heartbeat",
        json={
            "machine_id": "m",
            "location_tier": "home",
            "version": "0.5.0",
            "latency_self_ms": 12,
        },
    )
    assert response.status_code == 204
    daemons = client.get("/api/fleet/daemons").json()
    assert daemons[0]["online"] is True
    assert daemons[0]["latency_ms"] == 12


def test_state_update_appends_cli_state(client: TestClient) -> None:
    client.post(
        "/api/fleet/register",
        json={"machine_id": "m", "hostname": "h", "location_tier": "home", "version": "0.5.0"},
    )
    response = client.post(
        "/api/fleet/state",
        json={
            "machine_id": "m",
            "cli": "claude",
            "state": {"running": True, "rotation": 7},
        },
    )
    assert response.status_code == 204
    daemons = client.get("/api/fleet/daemons").json()
    assert daemons[0]["snapper_clis"] == ["claude"]


def test_state_update_unknown_machine_404(client: TestClient) -> None:
    response = client.post(
        "/api/fleet/state",
        json={"machine_id": "nope", "cli": "claude", "state": {}},
    )
    assert response.status_code == 404


def test_list_daemons_empty(client: TestClient) -> None:
    assert client.get("/api/fleet/daemons").json() == []


def test_revoke_removes_record(client: TestClient) -> None:
    client.post(
        "/api/fleet/register",
        json={"machine_id": "m", "hostname": "h", "location_tier": "home", "version": "0.5.0"},
    )
    response = client.delete("/api/fleet/daemons/m")
    assert response.status_code == 204
    assert client.get("/api/fleet/daemons").json() == []


def test_revoke_unknown_returns_404(client: TestClient) -> None:
    assert client.delete("/api/fleet/daemons/nope").status_code == 404
