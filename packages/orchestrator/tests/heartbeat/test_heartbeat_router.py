"""S-Auto Faz G — Heartbeat HTTP router tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.heartbeat_router import (
    build_heartbeat_router,
)
from selffork_orchestrator.heartbeat.autonomy import (
    AutonomyPreset,
    AutonomyStore,
    apply_preset,
)
from selffork_orchestrator.heartbeat.config import HeartbeatConfig
from selffork_orchestrator.heartbeat.deliberation import (
    DeliberationLayer,
)
from selffork_orchestrator.heartbeat.executor import ActionExecutor
from selffork_orchestrator.heartbeat.scheduler import HeartbeatScheduler
from selffork_orchestrator.telegram.inbound_router import PauseSignal


def _client(
    *,
    store: AutonomyStore,
    scheduler: HeartbeatScheduler | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(
        build_heartbeat_router(store=store, scheduler=scheduler),
    )
    return TestClient(app)


# ── GET/PUT autonomy ────────────────────────────────────────────


def test_get_autonomy_returns_default_when_absent(tmp_path: Path) -> None:
    store = AutonomyStore(path=tmp_path / "autonomy.yaml")
    response = _client(store=store).get("/api/heartbeat/autonomy")
    assert response.status_code == 200
    payload = response.json()
    assert payload["preset"] == "dengeli"
    assert payload["enabled"] is True


def test_get_autonomy_returns_persisted_settings(tmp_path: Path) -> None:
    store = AutonomyStore(path=tmp_path / "autonomy.yaml")
    store.write(apply_preset(AutonomyPreset.TAM))
    response = _client(store=store).get("/api/heartbeat/autonomy")
    assert response.status_code == 200
    payload = response.json()
    assert payload["preset"] == "tam"
    assert payload["creative_dial"] == "spark_only"


def test_put_autonomy_persists_settings(tmp_path: Path) -> None:
    store = AutonomyStore(path=tmp_path / "autonomy.yaml")
    body = apply_preset(AutonomyPreset.DENETIMLI).model_dump(mode="json")
    response = _client(store=store).put("/api/heartbeat/autonomy", json=body)
    assert response.status_code == 200
    persisted = store.read()
    assert persisted is not None
    assert persisted.preset is AutonomyPreset.DENETIMLI
    assert persisted.supervised_mode is True


def test_put_autonomy_rejects_unknown_field(tmp_path: Path) -> None:
    store = AutonomyStore(path=tmp_path / "autonomy.yaml")
    response = _client(store=store).put(
        "/api/heartbeat/autonomy",
        json={"preset": "dengeli", "unknown_field": 1},
    )
    # FastAPI returns 422 on pydantic validation failures.
    assert response.status_code == 422


# ── POST /autonomy/preset/{name} ────────────────────────────────


@pytest.mark.parametrize(
    "preset",
    ["kapalı", "denetimli", "dengeli", "tam"],
)
def test_post_preset_applies_each_tier(tmp_path: Path, preset: str) -> None:
    store = AutonomyStore(path=tmp_path / "autonomy.yaml")
    response = _client(store=store).post(f"/api/heartbeat/autonomy/preset/{preset}")
    assert response.status_code == 200
    persisted = store.read()
    assert persisted is not None
    assert persisted.preset.value == preset


def test_post_preset_rejects_unknown(tmp_path: Path) -> None:
    store = AutonomyStore(path=tmp_path / "autonomy.yaml")
    response = _client(store=store).post("/api/heartbeat/autonomy/preset/bogus")
    assert response.status_code == 400


# ── GET /state ──────────────────────────────────────────────────


def test_state_without_scheduler_returns_disabled(tmp_path: Path) -> None:
    store = AutonomyStore(path=tmp_path / "autonomy.yaml")
    response = _client(store=store).get("/api/heartbeat/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "disabled"
    assert payload["is_running"] is False
    assert payload["tick_count"] == 0
    assert payload["last_legal_actions"] is None


@pytest.mark.asyncio
async def test_state_with_running_scheduler(tmp_path: Path) -> None:
    """End-to-end: drive a tick + read the live state through the API."""

    class _StubSpeaker:
        async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
            return '{"action": "bekle", "reasoning": "iş yok"}'

    pause = PauseSignal(flag_path=tmp_path / "pause.flag")
    config = HeartbeatConfig(
        enabled=True,
        tick_seconds=0.02,
        reconciliation_seconds=0.05,
    )
    scheduler = HeartbeatScheduler(
        config=config,
        pause_signal=pause,
        deliberation_layer=DeliberationLayer(speaker=_StubSpeaker()),
        action_executor=ActionExecutor(),
    )
    store = AutonomyStore(path=tmp_path / "autonomy.yaml")
    try:
        await scheduler.start()
        import asyncio

        await asyncio.sleep(0.1)
        # TestClient is sync but the underlying scheduler is in the
        # same event loop; spawn a synchronous read via TestClient.
        client = TestClient(_build_app(store=store, scheduler=scheduler))
        response = client.get("/api/heartbeat/state")
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "running"
        assert payload["tick_count"] >= 1
        assert payload["last_legal_actions"] is not None
        assert payload["last_decision"]["action"] == "bekle"
        assert payload["last_result"]["outcome"] == "executed"
    finally:
        await scheduler.stop()


def _build_app(
    *,
    store: AutonomyStore,
    scheduler: HeartbeatScheduler,
) -> FastAPI:
    app = FastAPI()
    app.include_router(
        build_heartbeat_router(store=store, scheduler=scheduler),
    )
    return app
