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

    def test_update_card_partial_patch_preserves_order(self, tmp_path: Path) -> None:
        # Order 1 #1.A regression: title-only PATCH used to silently
        # clear ``order`` to None because the endpoint always passed
        # ``order=None`` into the store. Now the Pydantic v2
        # ``model_fields_set`` filter keeps ``order`` untouched.
        client, config = _client(tmp_path)
        store = ProjectStore(root=config.projects_root)
        store.create(name="X")
        card = store.add_card("x", title="t", order=42)
        r = client.patch(
            f"/api/projects/x/kanban/cards/{card.id}",
            json={"title": "renamed"},
        )
        assert r.status_code == 200
        assert r.json()["title"] == "renamed"
        assert r.json()["order"] == 42

        # Explicit ``order=null`` still clears the value (sentinel intact).
        r2 = client.patch(
            f"/api/projects/x/kanban/cards/{card.id}",
            json={"order": None},
        )
        assert r2.status_code == 200
        assert r2.json()["order"] is None

        # Explicit ``order=7`` updates the value.
        r3 = client.patch(
            f"/api/projects/x/kanban/cards/{card.id}",
            json={"order": 7},
        )
        assert r3.status_code == 200
        assert r3.json()["order"] == 7

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


# ── S7 — Project edit + archive + autopilot pause (ADR-007 §4 S7) ────────


class TestUpdateProject:
    def test_partial_patch_description(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="Calc")
        r = client.put("/api/projects/calc", json={"description": "calculator"})
        assert r.status_code == 200
        body = r.json()
        assert body["description"] == "calculator"
        assert body["name"] == "Calc"

    def test_rename(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="X")
        r = client.put("/api/projects/x", json={"name": "Better Name"})
        assert r.status_code == 200
        # Slug is stable; only the human-readable name changes.
        assert r.json()["slug"] == "x"
        assert r.json()["name"] == "Better Name"

    def test_clear_root_path_via_empty_string(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(
            name="P",
            root_path="/tmp/foo",
        )
        r = client.put("/api/projects/p", json={"root_path": ""})
        assert r.status_code == 200
        assert r.json()["root_path"] is None

    def test_set_root_path(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="Q")
        r = client.put("/api/projects/q", json={"root_path": "/tmp/zzz"})
        assert r.status_code == 200
        assert r.json()["root_path"] == "/tmp/zzz"

    def test_unknown_slug_404(self, tmp_path: Path) -> None:
        client, _ = _client(tmp_path)
        r = client.put("/api/projects/nope", json={"name": "X"})
        assert r.status_code == 404


class TestArchiveUnarchive:
    def test_archive_sets_timestamp(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="Z")
        r = client.post("/api/projects/z/archive")
        assert r.status_code == 200
        body = r.json()
        assert body["archived_at"] is not None
        # Persists across reads.
        r2 = client.get("/api/projects/z")
        assert r2.json()["archived_at"] == body["archived_at"]

    def test_archive_filters_default_listing(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="Live")
        ProjectStore(root=config.projects_root).create(name="Old")
        client.post("/api/projects/old/archive")
        # Default listing hides archived.
        r = client.get("/api/projects")
        slugs = [p["slug"] for p in r.json()]
        assert "live" in slugs
        assert "old" not in slugs
        # ``?include_archived=true`` returns both.
        r2 = client.get("/api/projects?include_archived=true")
        slugs2 = [p["slug"] for p in r2.json()]
        assert "live" in slugs2
        assert "old" in slugs2

    def test_unarchive_clears_timestamp(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="Y")
        client.post("/api/projects/y/archive")
        r = client.post("/api/projects/y/unarchive")
        assert r.status_code == 200
        assert r.json()["archived_at"] is None
        # Re-appears in default listing.
        r2 = client.get("/api/projects")
        assert "y" in [p["slug"] for p in r2.json()]

    def test_archive_unknown_slug_404(self, tmp_path: Path) -> None:
        client, _ = _client(tmp_path)
        r = client.post("/api/projects/nope/archive")
        assert r.status_code == 404


class TestAutopilotPause:
    def test_pause_sets_flag(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="A")
        r = client.post("/api/projects/a/autopilot/pause")
        assert r.status_code == 200
        body = r.json()
        assert body["autopilot_paused"] is True
        # Persists across reads.
        r2 = client.get("/api/projects/a")
        assert r2.json()["autopilot_paused"] is True

    def test_resume_clears_flag(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="B")
        client.post("/api/projects/b/autopilot/pause")
        r = client.post("/api/projects/b/autopilot/resume")
        assert r.status_code == 200
        assert r.json()["autopilot_paused"] is False

    def test_pause_idempotent(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="C")
        client.post("/api/projects/c/autopilot/pause")
        r = client.post("/api/projects/c/autopilot/pause")
        assert r.status_code == 200
        assert r.json()["autopilot_paused"] is True

    def test_pause_unknown_slug_404(self, tmp_path: Path) -> None:
        client, _ = _client(tmp_path)
        r = client.post("/api/projects/nope/autopilot/pause")
        assert r.status_code == 404


class TestProjectResponseShape:
    """ADR-007 §4 S7 wire-shape contract — new fields land on every
    project response surface so the frontend can rely on them."""

    def test_create_response_has_s7_fields(self, tmp_path: Path) -> None:
        client, _ = _client(tmp_path)
        body = client.post("/api/projects", json={"name": "S"}).json()
        assert body["archived_at"] is None
        assert body["autopilot_paused"] is False

    def test_get_response_has_s7_fields(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="T")
        body = client.get("/api/projects/t").json()
        assert "archived_at" in body
        assert "autopilot_paused" in body

    def test_list_response_has_s7_fields(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        ProjectStore(root=config.projects_root).create(name="U")
        rows = client.get("/api/projects").json()
        assert len(rows) == 1
        assert rows[0]["archived_at"] is None
        assert rows[0]["autopilot_paused"] is False
