"""Integration tests for the Live Run Theater router — S2.

Real :class:`TheaterStore` on tmp_path (no mocks). A test seeds the
theater DB the way a ``selffork run`` process would, then asserts the
dashboard router serves it.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.server import DashboardConfig, build_app
from selffork_orchestrator.dashboard.theater_router import (
    build_loop_router,
    build_theater_router,
)
from selffork_orchestrator.theater.store import open_theater_store


def _setup(tmp_path: Path, slug: str) -> tuple[TestClient, Path]:
    """Build a theater + loop router app; create the workspace dir."""
    projects_root = tmp_path / "projects"
    (projects_root / slug).mkdir(parents=True)
    db_path = tmp_path / "theater" / "events.db"
    app = FastAPI()
    app.include_router(build_theater_router(projects_root=projects_root, db_path=db_path))
    app.include_router(build_loop_router(db_path=db_path))
    return TestClient(app), db_path


def _seed_cli_output(db_path: Path, slug: str, text: str) -> None:
    async def _run() -> None:
        async with open_theater_store(db_path) as store:
            await store.append_event(
                workspace_slug=slug,
                session_id="sess",
                kind="cli_output",
                payload={"kind": "stdout", "text": text},
            )

    asyncio.run(_run())


def _seed_thought(db_path: Path, slug: str, summary: str) -> None:
    async def _run() -> None:
        async with open_theater_store(db_path) as store:
            await store.append_event(
                workspace_slug=slug,
                session_id="sess",
                kind="thought",
                payload={"summary": summary},
            )

    asyncio.run(_run())


def _seed_loop(db_path: Path, slug: str, *, cli: str, turn: int) -> None:
    async def _run() -> None:
        async with open_theater_store(db_path) as store:
            await store.register_loop(
                session_id="sess",
                workspace_slug=slug,
                workspace_name=f"{slug} display",
                cli=cli,
            )
            if turn:
                await store.touch_loop(session_id="sess", turn=turn)

    asyncio.run(_run())


# ── Snapshot ─────────────────────────────────────────────────────────────────


class TestSnapshot:
    def test_empty_workspace_idle(self, tmp_path: Path) -> None:
        client, _ = _setup(tmp_path, "proj-x")
        body = client.get("/api/workspaces/proj-x/theater/snapshot").json()
        assert body["active"] is False
        assert body["output"] == []
        assert body["thoughts"] == []
        assert body["screenshots"] == []

    def test_includes_cli_output_and_thoughts(self, tmp_path: Path) -> None:
        client, db = _setup(tmp_path, "proj-x")
        _seed_cli_output(db, "proj-x", "npm run dev")
        _seed_thought(db, "proj-x", "Testing the login flow")
        body = client.get("/api/workspaces/proj-x/theater/snapshot").json()
        assert [c["text"] for c in body["output"]] == ["npm run dev"]
        assert [t["summary"] for t in body["thoughts"]] == ["Testing the login flow"]

    def test_reflects_active_loop(self, tmp_path: Path) -> None:
        client, db = _setup(tmp_path, "proj-x")
        _seed_loop(db, "proj-x", cli="claude", turn=4)
        body = client.get("/api/workspaces/proj-x/theater/snapshot").json()
        assert body["active"] is True
        assert body["cli"] == "claude"
        assert body["turn"] == 4

    def test_unknown_workspace_404(self, tmp_path: Path) -> None:
        client, _ = _setup(tmp_path, "proj-x")
        r = client.get("/api/workspaces/ghost/theater/snapshot")
        assert r.status_code == 404


# ── Active loop ──────────────────────────────────────────────────────────────


class TestActiveLoop:
    def test_idle_returns_null(self, tmp_path: Path) -> None:
        client, _ = _setup(tmp_path, "proj-x")
        r = client.get("/api/loop/active")
        assert r.status_code == 200
        assert r.json() is None

    def test_returns_active_loop(self, tmp_path: Path) -> None:
        client, db = _setup(tmp_path, "proj-x")
        _seed_loop(db, "proj-x", cli="gemini", turn=2)
        body = client.get("/api/loop/active").json()
        assert body is not None
        assert body["workspace_slug"] == "proj-x"
        assert body["workspace_name"] == "proj-x display"
        assert body["cli"] == "gemini"
        assert body["turn"] == 2


# ── WS stream ────────────────────────────────────────────────────────────────


class TestStream:
    def test_first_frame_is_snapshot(self, tmp_path: Path) -> None:
        client, db = _setup(tmp_path, "ws-snap")
        _seed_cli_output(db, "ws-snap", "hello")
        with client.websocket_connect("/api/workspaces/ws-snap/theater/stream") as ws:
            frame = json.loads(ws.receive_text())
            assert frame["event_type"] == "snapshot"
            assert [c["text"] for c in frame["payload"]["output"]] == ["hello"]

    def test_tails_new_event(self, tmp_path: Path) -> None:
        client, db = _setup(tmp_path, "ws-tail")
        with client.websocket_connect("/api/workspaces/ws-tail/theater/stream") as ws:
            snap = json.loads(ws.receive_text())
            assert snap["event_type"] == "snapshot"
            # A fresh event lands after connect — Phase 2 poll surfaces it.
            _seed_cli_output(db, "ws-tail", "live line")
            frame = json.loads(ws.receive_text())
            assert frame["event_type"] == "cli.output.append"
            assert frame["payload"]["text"] == "live line"

    def test_unknown_workspace_closes(self, tmp_path: Path) -> None:
        client, _ = _setup(tmp_path, "ws-real")
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect("/api/workspaces/ws-ghost/theater/stream") as ws,
        ):
            ws.receive_text()

    def test_tails_new_thought(self, tmp_path: Path) -> None:
        client, db = _setup(tmp_path, "ws-thought")
        with client.websocket_connect("/api/workspaces/ws-thought/theater/stream") as ws:
            snap = json.loads(ws.receive_text())
            assert snap["event_type"] == "snapshot"
            _seed_thought(db, "ws-thought", "Reviewing the auth flow")
            frame = json.loads(ws.receive_text())
            assert frame["event_type"] == "thought.new"
            assert frame["payload"]["summary"] == "Reviewing the auth flow"

    def test_reconnect_still_serves_persisted_events(self, tmp_path: Path) -> None:
        client, db = _setup(tmp_path, "ws-reconn")
        _seed_cli_output(db, "ws-reconn", "before reconnect")
        with client.websocket_connect("/api/workspaces/ws-reconn/theater/stream") as ws:
            ws.receive_text()
        # A fresh reconnect must re-sync the persisted stream via a
        # snapshot frame (drain past any replayed frames to find it).
        with client.websocket_connect("/api/workspaces/ws-reconn/theater/stream") as ws:
            snap = None
            for _ in range(5):
                frame = json.loads(ws.receive_text())
                if frame["event_type"] == "snapshot":
                    snap = frame
                    break
            assert snap is not None
            assert [c["text"] for c in snap["payload"]["output"]] == ["before reconnect"]


# ── Build-app wiring ─────────────────────────────────────────────────────────


class TestWiring:
    def test_theater_routers_mounted_on_full_app(self, tmp_path: Path) -> None:
        config = DashboardConfig(
            audit_dir=tmp_path / "audit",
            resume_dir=tmp_path / "scheduled",
            projects_root=tmp_path / "projects",
            selffork_script=tmp_path / "fake-selffork",
        )
        for directory in (
            config.audit_dir,
            config.resume_dir,
            config.projects_root,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        (config.projects_root / "proj-x").mkdir()
        client = TestClient(build_app(config))
        assert client.get("/api/loop/active").json() is None
        snap = client.get("/api/workspaces/proj-x/theater/snapshot")
        assert snap.status_code == 200
        assert snap.json()["active"] is False
