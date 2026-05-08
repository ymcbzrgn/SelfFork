"""Tests for the dashboard's Mind provenance endpoint (Order 5)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.server import (
    DashboardConfig,
    build_app,
)


def _client(tmp_path: Path) -> TestClient:
    config = DashboardConfig(
        audit_dir=tmp_path / "audit",
        resume_dir=tmp_path / "scheduled",
        projects_root=tmp_path / "projects",
        selffork_script=Path("/usr/bin/true"),
    )
    config.audit_dir.mkdir(parents=True, exist_ok=True)
    config.resume_dir.mkdir(parents=True, exist_ok=True)
    config.projects_root.mkdir(parents=True, exist_ok=True)
    return TestClient(build_app(config))


def _write_provenance(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    base = datetime.now(UTC) - timedelta(seconds=count)
    with path.open("w", encoding="utf-8") as f:
        for i in range(count):
            payload = {
                "ts": (base + timedelta(seconds=i)).isoformat(),
                "correlation_id": f"corr-{i}",
                "session_id": "s1",
                "project_slug": "alpha",
                "query": f"query {i}",
                "note_ids": [str(uuid4())],
                "scores": [0.5 + 0.1 * i],
                "retriever": "vector:none",
                "reranker": None,
            }
            f.write(json.dumps(payload) + "\n")


@pytest.mark.anyio
async def test_project_provenance_endpoint_empty(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/projects/alpha/mind/provenance")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_project_provenance_endpoint_returns_entries(tmp_path: Path) -> None:
    log = tmp_path / "projects" / "alpha" / "mind" / "provenance.jsonl"
    _write_provenance(log, count=3)
    client = _client(tmp_path)
    response = client.get("/api/projects/alpha/mind/provenance")
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 3
    for entry in entries:
        assert "query" in entry
        assert "note_ids" in entry
        assert isinstance(entry["scores"], list)


@pytest.mark.anyio
async def test_project_provenance_endpoint_limit(tmp_path: Path) -> None:
    log = tmp_path / "projects" / "alpha" / "mind" / "provenance.jsonl"
    _write_provenance(log, count=10)
    client = _client(tmp_path)
    response = client.get("/api/projects/alpha/mind/provenance?limit=4")
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 4


@pytest.mark.anyio
async def test_orphan_provenance_endpoint_empty(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/mind/provenance")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_orphan_provenance_endpoint_returns_entries(tmp_path: Path) -> None:
    # Orphan layout: ~/.selffork/mind/provenance.jsonl — sibling of audit_dir.
    log = tmp_path / "mind" / "provenance.jsonl"
    _write_provenance(log, count=2)
    client = _client(tmp_path)
    response = client.get("/api/mind/provenance")
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 2
