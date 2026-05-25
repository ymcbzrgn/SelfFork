"""provider_router REST surface — list / sign_in_start / refresh / disconnect.

``list_providers`` overlays on-disk auth status (the operator signs in
CLI-natively, [[cli-provider-routing]]); these tests inject a fake
``creds_detector`` so they never touch the real home dir / keychain.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.provider_creds import ProviderAuthStatus
from selffork_orchestrator.dashboard.provider_router import (
    ProviderRegistry,
    build_provider_router,
)

_PROVIDER_NAMES = ("claude_pro", "codex", "gemini", "opencode", "mmx")


def _all_disconnected() -> dict[str, ProviderAuthStatus]:
    return {n: ProviderAuthStatus("disconnected") for n in _PROVIDER_NAMES}


@pytest.fixture()
def registry() -> ProviderRegistry:
    return ProviderRegistry()


def _build_client(
    registry: ProviderRegistry,
    detector: Callable[[], dict[str, ProviderAuthStatus]],
) -> TestClient:
    app = FastAPI()
    app.include_router(
        build_provider_router(registry=registry, creds_detector=detector)
    )
    return TestClient(app)


@pytest.fixture()
def client(registry: ProviderRegistry) -> TestClient:
    # Default: everything disconnected, so status assertions are
    # deterministic regardless of the developer's real ~/.codex etc.
    return _build_client(registry, _all_disconnected)


def test_list_providers_returns_five(client: TestClient) -> None:
    response = client.get("/api/providers")
    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body}
    assert names == {"claude_pro", "codex", "gemini", "opencode", "mmx"}
    for item in body:
        assert item["status"] == "disconnected"


def test_list_providers_reflects_disk_connected(
    registry: ProviderRegistry,
) -> None:
    """On-disk creds flip a provider to connected without any sign-in flow."""

    def detector() -> dict[str, ProviderAuthStatus]:
        status = _all_disconnected()
        status["codex"] = ProviderAuthStatus("connected", detail="/h/.codex/auth.json")
        status["opencode"] = ProviderAuthStatus("connected")
        return status

    client = _build_client(registry, detector)
    body = client.get("/api/providers").json()
    by_name = {item["name"]: item for item in body}
    assert by_name["codex"]["status"] == "connected"
    assert by_name["opencode"]["status"] == "connected"
    assert by_name["gemini"]["status"] == "disconnected"


def test_list_providers_reflects_disk_expired(
    registry: ProviderRegistry,
) -> None:
    """An expiry-carrying provider surfaces expired + expires_at."""

    def detector() -> dict[str, ProviderAuthStatus]:
        from datetime import UTC, datetime

        status = _all_disconnected()
        status["gemini"] = ProviderAuthStatus(
            "expired",
            expires_at=datetime(2020, 1, 1, tzinfo=UTC),
            detail="/h/.gemini/oauth_creds.json",
        )
        return status

    client = _build_client(registry, detector)
    body = client.get("/api/providers").json()
    gemini = next(i for i in body if i["name"] == "gemini")
    assert gemini["status"] == "expired"
    assert gemini["expires_at"] is not None


def test_list_providers_disk_wins_but_preserves_last_error(
    registry: ProviderRegistry,
) -> None:
    """Disk status is authoritative; the auth-expired alert reason stays
    visible (the operator re-signed-in via CLI → disk now connected)."""
    registry.mark_failed("codex", "auth_expired: 401 from upstream")

    def detector() -> dict[str, ProviderAuthStatus]:
        status = _all_disconnected()
        status["codex"] = ProviderAuthStatus("connected")
        return status

    client = _build_client(registry, detector)
    codex = next(
        i for i in client.get("/api/providers").json() if i["name"] == "codex"
    )
    assert codex["status"] == "connected"
    assert codex["last_error"] == "auth_expired: 401 from upstream"


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


def test_disconnect_marks_status(
    client: TestClient, registry: ProviderRegistry
) -> None:
    record = registry.mark_signed_in("codex", storage_state_path="/tmp/codex.json")
    assert record.status == "connected"
    response = client.post("/api/providers/codex/disconnect")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disconnected"
    assert body["storage_state_path"] is None


def test_disconnect_unknown_provider_404(client: TestClient) -> None:
    assert client.post("/api/providers/nope/disconnect").status_code == 404
