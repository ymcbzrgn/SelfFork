"""body_router REST surface — list / get / stop / permission decide."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from selffork_body.sandbox import (
    BodyWatchdog,
    PermissionWarden,
    WardenMode,
    build_request,
)
from selffork_orchestrator.dashboard.body_router import build_body_router


@pytest.fixture()
def watchdog() -> BodyWatchdog:
    return BodyWatchdog(poll_interval_sec=10.0)


@pytest.fixture()
def app(watchdog: BodyWatchdog) -> FastAPI:
    a = FastAPI()
    a.include_router(build_body_router(watchdog=watchdog))
    return a


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_list_sessions_empty(client: TestClient) -> None:
    response = client.get("/api/body/sessions")
    assert response.status_code == 200
    assert response.json() == []


def test_list_sessions_with_one(client: TestClient, watchdog: BodyWatchdog) -> None:
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE)
    watchdog.register(session_id="sess-A", warden=warden)
    response = client.get("/api/body/sessions")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["session_id"] == "sess-A"
    assert body[0]["killed"] is False


def test_get_session_not_found(client: TestClient) -> None:
    response = client.get("/api/body/sessions/missing")
    assert response.status_code == 404


def test_stop_session_kills(client: TestClient, watchdog: BodyWatchdog) -> None:
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE)
    watchdog.register(session_id="sess-B", warden=warden)
    response = client.post(
        "/api/body/sessions/sess-B/stop", json={"reason": "ui_button"}
    )
    assert response.status_code == 202
    assert response.json() == {"status": "killed"}


def test_stop_session_already_killed(client: TestClient, watchdog: BodyWatchdog) -> None:
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE)
    watchdog.register(session_id="sess-C", warden=warden)
    watchdog.kill_session("sess-C", "first")
    response = client.post(
        "/api/body/sessions/sess-C/stop", json={"reason": "second"}
    )
    assert response.status_code == 202
    assert response.json() == {"status": "already_killed"}


def test_stop_session_not_found_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/body/sessions/nope/stop", json={"reason": "x"}
    )
    assert response.status_code == 404


def test_decide_permission_approves_pending_request() -> None:
    watchdog = BodyWatchdog(poll_interval_sec=10.0)
    warden = PermissionWarden(mode=WardenMode.WORKSPACE_WRITE, default_timeout_sec=2.0)
    watchdog.register(session_id="sess-D", warden=warden)
    registry = {"sess-D": warden}
    fresh_app = FastAPI()
    fresh_app.include_router(
        build_body_router(watchdog=watchdog, warden_registry=registry)
    )
    client = TestClient(fresh_app)

    req = build_request(
        request_id="r-decide",
        session_id="sess-D",
        action_type="shell_exec",
    )

    async def _run() -> tuple[dict, dict]:
        decision_task = asyncio.create_task(warden.request(req))
        await asyncio.sleep(0.02)
        response = client.post(
            "/api/body/permissions/r-decide",
            json={"approved": True, "reason": "ui_approve"},
        )
        decision = await decision_task
        return response.json(), {
            "approved": decision.approved,
            "decision": decision.decision,
            "decided_by": decision.decided_by,
        }

    rest_body, decision_view = asyncio.run(_run())
    assert rest_body == {"matched": True, "decision": "approved"}
    assert decision_view["approved"] is True
    assert decision_view["decided_by"] == "operator"


def test_decide_permission_unknown_request_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/body/permissions/missing-id", json={"approved": True, "reason": "x"}
    )
    assert response.status_code == 404
