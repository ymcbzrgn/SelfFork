"""ADR-009 §5 — dashboard lifespan spawns the Mind heartbeat/correction
ingesters (opt-in + fail-soft).

Follows the ``test_server.py`` pattern: a real tmp-rooted
:class:`DashboardConfig`, the app built via :func:`build_app`, and the
lifespan exercised by entering the :class:`fastapi.testclient.TestClient`
context manager (which runs startup + shutdown).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from selffork_mind.ingest.heartbeat import (
    CorrectionIngester,
    HeartbeatIngester,
)
from selffork_orchestrator.dashboard.activity import (
    default_heartbeat_audit_path,
)
from selffork_orchestrator.dashboard.server import (
    DashboardConfig,
    build_app,
)
from selffork_shared.config import MindConfig


def _build_config(tmp_path: Path) -> DashboardConfig:
    config = DashboardConfig(
        audit_dir=tmp_path / "audit",
        resume_dir=tmp_path / "scheduled",
        projects_root=tmp_path / "projects",
        selffork_script=tmp_path / "fake-selffork",
        mind_config=MindConfig(
            storage_root=str(tmp_path / "mind"), embedder="none"
        ),
        cli_affinity_home=tmp_path / "affinity",
    )
    config.audit_dir.mkdir(parents=True, exist_ok=True)
    config.resume_dir.mkdir(parents=True, exist_ok=True)
    config.projects_root.mkdir(parents=True, exist_ok=True)
    return config


def _seed_heartbeat_audit(config: DashboardConfig) -> Path:
    audit_path = default_heartbeat_audit_path(config.audit_dir)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "tick": 1,
        "timestamp": "2026-05-24T03:12:55+00:00",
        "trigger": "reconciliation",
        "world_state": {"last_active_workspace": None},
        "legal_actions": ["WAIT"],
        "decision_action": "bekle",
        "result_outcome": "executed",
        "air_alert": None,
        "idempotency_key": "tick-1",
    }
    audit_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    return audit_path


def _isolate_heartbeat(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep the Heartbeat daemon disabled regardless of the operator's
    real ``~/.selffork/heartbeat/autonomy.yaml`` (mirrors the heartbeat
    test suite's isolation)."""
    monkeypatch.setattr(
        "selffork_orchestrator.heartbeat.autonomy.default_autonomy_path",
        lambda: tmp_path / "autonomy.yaml",
    )


def test_mind_ingesters_spawned_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SELFFORK_MIND_INGEST_ENABLED", "true")
    _isolate_heartbeat(monkeypatch, tmp_path)
    config = _build_config(tmp_path)
    _seed_heartbeat_audit(config)

    app = build_app(config)
    with TestClient(app) as client:
        assert client.get("/api/sessions/recent").status_code == 200
        ingesters = app.state.mind_ingesters
        assert len(ingesters) == 2
        assert isinstance(ingesters[0], HeartbeatIngester)
        assert isinstance(ingesters[1], CorrectionIngester)
        # The heartbeat ingester tails the audit log derived from audit_dir.
        assert ingesters[0].audit_path == default_heartbeat_audit_path(
            config.audit_dir
        )
        assert len(app.state.mind_ingester_tasks) == 2


def test_mind_ingesters_disabled_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SELFFORK_MIND_INGEST_ENABLED", raising=False)
    _isolate_heartbeat(monkeypatch, tmp_path)
    config = _build_config(tmp_path)

    app = build_app(config)
    with TestClient(app) as client:
        assert client.get("/api/sessions/recent").status_code == 200
        assert app.state.mind_ingesters == []
        assert app.state.mind_ingester_tasks == []


def test_mind_ingesters_failsoft_when_store_open_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SELFFORK_MIND_INGEST_ENABLED", "true")
    _isolate_heartbeat(monkeypatch, tmp_path)

    async def _boom(*, root: Path) -> object:
        raise RuntimeError("cannot open store")

    monkeypatch.setattr(
        "selffork_orchestrator.dashboard.mind_deps.open_store", _boom
    )
    config = _build_config(tmp_path)

    app = build_app(config)
    with TestClient(app) as client:
        # Startup completed despite the ingester open failure.
        assert client.get("/api/sessions/recent").status_code == 200
        assert app.state.mind_ingesters == []
        assert app.state.mind_ingester_tasks == []
