"""Integration tests for /api/projects + /api/usage/providers endpoints.

Real ProjectStore + UsageAggregator, no mocks. Each test stages
its own filesystem state, calls the API via TestClient, asserts the
on-disk artefact OR response shape.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.server import (
    DashboardConfig,
    build_app,
)
from selffork_orchestrator.projects.store import ProjectStore


def _client(tmp_path: Path) -> tuple[TestClient, DashboardConfig]:
    config = DashboardConfig(
        audit_dir=tmp_path / "audit",
        resume_dir=tmp_path / "scheduled",
        projects_root=tmp_path / "projects",
        selffork_script=tmp_path / "fake-selffork",
    )
    config.audit_dir.mkdir(parents=True, exist_ok=True)
    config.resume_dir.mkdir(parents=True, exist_ok=True)
    config.projects_root.mkdir(parents=True, exist_ok=True)
    return TestClient(build_app(config)), config


# ── /api/projects (list, create, get) ────────────────────────────────────────


class TestListProjects:
    def test_empty(self, tmp_path: Path) -> None:
        client, _ = _client(tmp_path)
        r = client.get("/api/projects")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_card_counts(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        store = ProjectStore(root=config.projects_root)
        store.create(name="Calc")
        store.add_card("calc", title="Build add()")
        c = store.add_card("calc", title="Build sub()")
        store.move_card("calc", c.id, to_column="done")

        r = client.get("/api/projects")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        row = rows[0]
        assert row["slug"] == "calc"
        assert row["card_counts"]["backlog"] == 1
        assert row["card_counts"]["done"] == 1


class TestCreateProject:
    def test_minimum_payload(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        r = client.post("/api/projects", json={"name": "My Project"})
        assert r.status_code == 201
        body = r.json()
        assert body["slug"] == "my-project"
        assert body["card_counts"] == {
            "backlog": 0,
            "in_progress": 0,
            "review": 0,
            "done": 0,
        }
        # On-disk side: project.json + kanban.json exist.
        proj_dir = config.projects_root / "my-project"
        assert (proj_dir / "project.json").is_file()
        assert (proj_dir / "kanban.json").is_file()

    def test_duplicate_returns_400(self, tmp_path: Path) -> None:
        client, _ = _client(tmp_path)
        client.post("/api/projects", json={"name": "Dup"})
        r = client.post("/api/projects", json={"name": "Dup"})
        assert r.status_code == 400
        assert "already exists" in r.json()["detail"]

    def test_invalid_name_returns_400(self, tmp_path: Path) -> None:
        client, _ = _client(tmp_path)
        r = client.post("/api/projects", json={"name": "!!!"})
        assert r.status_code == 400


class TestGetProject:
    def test_unknown_slug_404(self, tmp_path: Path) -> None:
        client, _ = _client(tmp_path)
        r = client.get("/api/projects/nope")
        assert r.status_code == 404


# ── /api/projects/<slug>/kanban ──────────────────────────────────────────────


class TestKanban:
    def test_empty_board(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="Empty")
        r = client.get("/api/projects/empty/kanban")
        assert r.status_code == 200
        body = r.json()
        assert body["columns"] == ["backlog", "in_progress", "review", "done"]
        for col in body["columns"]:
            assert body["cards_by_column"][col] == []

    def test_add_card(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="Board")
        r = client.post(
            "/api/projects/board/kanban/cards",
            json={"title": "Build add()", "body": "do it"},
        )
        assert r.status_code == 201
        card = r.json()
        assert card["title"] == "Build add()"
        assert card["column"] == "backlog"

    def test_add_card_with_invalid_column_400(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="X")
        r = client.post(
            "/api/projects/x/kanban/cards",
            json={"title": "t", "column": "nope"},
        )
        assert r.status_code == 400

    def test_move_card_to_done(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        store = ProjectStore(root=config.projects_root)
        store.create(name="X")
        card = store.add_card("x", title="t")
        r = client.patch(
            f"/api/projects/x/kanban/cards/{card.id}/move",
            json={"to_column": "done"},
        )
        assert r.status_code == 200
        assert r.json()["column"] == "done"
        assert r.json()["completed_at"] is not None

    def test_update_card(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        store = ProjectStore(root=config.projects_root)
        store.create(name="X")
        card = store.add_card("x", title="old")
        r = client.patch(
            f"/api/projects/x/kanban/cards/{card.id}",
            json={"title": "new", "body": "filled"},
        )
        assert r.status_code == 200
        assert r.json()["title"] == "new"
        assert r.json()["body"] == "filled"

    def test_delete_card(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        store = ProjectStore(root=config.projects_root)
        store.create(name="X")
        card = store.add_card("x", title="bye")
        r = client.delete(f"/api/projects/x/kanban/cards/{card.id}")
        assert r.status_code == 204
        assert store.load_board("x").cards == []

    def test_delete_unknown_card_404(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="X")
        r = client.delete("/api/projects/x/kanban/cards/missing")
        assert r.status_code == 404


# ── /api/usage/providers ─────────────────────────────────────────────────────


class TestUsageEndpoint:
    def test_empty(self, tmp_path: Path) -> None:
        client, _ = _client(tmp_path)
        r = client.get("/api/usage/providers")
        assert r.status_code == 200
        assert r.json() == []

    def test_includes_project_and_orphan_audits(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        # Orphan audit log under audit_dir.
        (config.audit_dir / "01HJ_orphan.jsonl").write_text(
            json.dumps(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "correlation_id": "x",
                    "session_id": "01HJ_orphan",
                    "category": "agent.invoke",
                    "level": "INFO",
                    "event": "test",
                    "payload": {
                        "round": 0,
                        "binary": "/Users/x/.local/bin/claude",
                        "args_count": 1,
                    },
                },
            )
            + "\n",
            encoding="utf-8",
        )
        # Per-project audit log.
        store = ProjectStore(root=config.projects_root)
        store.create(name="P")
        proj_audit = store.audit_dir("p")
        proj_audit.mkdir(parents=True)
        (proj_audit / "01HJ_proj.jsonl").write_text(
            json.dumps(
                {
                    "ts": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
                    "correlation_id": "x",
                    "session_id": "01HJ_proj",
                    "category": "agent.invoke",
                    "level": "INFO",
                    "event": "test",
                    "payload": {
                        "round": 0,
                        "binary": "/Users/x/.local/bin/claude",
                        "args_count": 1,
                    },
                },
            )
            + "\n",
            encoding="utf-8",
        )
        r = client.get("/api/usage/providers")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["cli_agent"] == "claude-code"
        # 2 invokes (1 orphan + 1 project) within the 5h window.
        assert rows[0]["calls_in_window"] == 2
