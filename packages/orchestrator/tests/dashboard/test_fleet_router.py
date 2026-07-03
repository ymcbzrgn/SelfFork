"""fleet_router REST surface — register / heartbeat / state / list / revoke."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from selffork_orchestrator.dashboard.fleet_router import (
    FleetRegistry,
    build_fleet_router,
)

SIGNED_COMMAND = {
    "command": "send_keys",
    "args": {"target": "dev:0", "keys": "ls"},
    "nonce": "n1",
    "timestamp": "2026-07-03T00:00:00Z",
    "signature": "deadbeefcafef00d",
}


def _register(client: TestClient, machine_id: str = "m") -> None:
    resp = client.post(
        "/api/fleet/register",
        json={
            "machine_id": machine_id,
            "hostname": "h",
            "location_tier": "home",
            "version": "0.5.0",
        },
    )
    assert resp.status_code == 201


@pytest.fixture()
def registry() -> FleetRegistry:
    # ``:memory:`` gives each test an isolated, off-disk DuckDB database.
    return FleetRegistry(online_grace_sec=60, db_path=":memory:")


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


# ---------------------------------------------------------------------------
# WebSocket command-intake channel (/ws/fleet/{machine_id})
# ---------------------------------------------------------------------------


def test_ws_rejects_unregistered_machine(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/fleet/ghost") as ws,
    ):
        ws.receive_text()


def test_ws_pushes_dispatched_command(client: TestClient) -> None:
    _register(client)
    with client.websocket_connect("/ws/fleet/m") as ws:
        resp = client.post("/api/fleet/dispatch/m", json=SIGNED_COMMAND)
        assert resp.status_code == 202
        assert resp.json() == {"status": "queued"}
        assert ws.receive_json() == SIGNED_COMMAND


def test_ws_delivers_command_queued_before_connect(client: TestClient) -> None:
    _register(client)
    # Dispatch before the daemon connects; the outbound queue buffers it.
    assert client.post("/api/fleet/dispatch/m", json=SIGNED_COMMAND).status_code == 202
    with client.websocket_connect("/ws/fleet/m") as ws:
        assert ws.receive_json() == SIGNED_COMMAND


def test_dispatch_unknown_machine_returns_404(client: TestClient) -> None:
    resp = client.post("/api/fleet/dispatch/ghost", json=SIGNED_COMMAND)
    assert resp.status_code == 404


def test_dispatch_rejects_malformed_command(client: TestClient) -> None:
    _register(client)
    # Missing the required "signature" field -> 422 from pydantic validation.
    resp = client.post(
        "/api/fleet/dispatch/m",
        json={"command": "send_keys", "nonce": "n1", "timestamp": "t"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DuckDB persistence — the roster + issued auth keys survive an orchestrator
# restart (simulated by a fresh FleetRegistry on the SAME db_path).
# ---------------------------------------------------------------------------


def test_registry_persists_roster_across_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "fleet.duckdb"

    async def scenario() -> None:
        # First "process": register + heartbeat + snapper-state, then close so
        # the DuckDB file lock is released (as a real process exit would).
        first = FleetRegistry(db_path=db_path)
        record = await first.register(
            machine_id="persist-1",
            hostname="persist-1.local",
            location_tier="home",
            version="0.5.0",
        )
        auth_key = record.auth_key
        await first.heartbeat(
            machine_id="persist-1",
            location_tier="work",
            version="0.6.0",
            latency_self_ms=21,
        )
        await first.update_state(
            machine_id="persist-1",
            cli="claude",
            state={"running": True, "rotation": 7},
        )
        await first.close()

        # Second "process": brand-new registry object on the SAME file.
        second = FleetRegistry(db_path=db_path)
        try:
            records = await second.list_records()
            assert len(records) == 1
            survived = records[0]
            assert survived.machine_id == "persist-1"
            # The auth key issued before the restart is recovered verbatim.
            assert survived.auth_key == auth_key
            # Heartbeat mutations persisted.
            assert survived.location_tier == "work"
            assert survived.version == "0.6.0"
            assert survived.latency_ms == 21
            assert survived.online is True
            assert survived.last_heartbeat is not None
            # Snapper-state delta persisted.
            assert survived.snapper_states["claude"] == {
                "running": True,
                "rotation": 7,
            }
        finally:
            await second.close()

    asyncio.run(scenario())


def test_registry_persists_revocation_across_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "fleet.duckdb"

    async def scenario() -> None:
        first = FleetRegistry(db_path=db_path)
        await first.register(
            machine_id="doomed",
            hostname="doomed.local",
            location_tier="home",
            version="0.5.0",
        )
        assert await first.revoke("doomed") is True
        await first.close()

        second = FleetRegistry(db_path=db_path)
        try:
            # Revocation is durable: the row is gone after restart.
            assert await second.list_records() == []
            # ...and the machine_id is free to re-register with a fresh key.
            reborn = await second.register(
                machine_id="doomed",
                hostname="doomed.local",
                location_tier="home",
                version="0.5.0",
            )
            assert reborn.auth_key
        finally:
            await second.close()

    asyncio.run(scenario())


def test_registry_duplicate_rejected_after_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "fleet.duckdb"

    async def scenario() -> None:
        first = FleetRegistry(db_path=db_path)
        await first.register(
            machine_id="dup",
            hostname="h",
            location_tier="home",
            version="0.5.0",
        )
        await first.close()

        # The primary-key constraint persists: re-registering the same id on a
        # restarted registry still raises, exactly as it did in-process.
        second = FleetRegistry(db_path=db_path)
        try:
            with pytest.raises(ValueError, match="already registered"):
                await second.register(
                    machine_id="dup",
                    hostname="h",
                    location_tier="home",
                    version="0.5.0",
                )
        finally:
            await second.close()

    asyncio.run(scenario())
