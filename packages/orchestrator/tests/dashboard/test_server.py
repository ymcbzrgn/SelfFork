"""Integration tests for the dashboard FastAPI app — REAL artifacts only.

Per ``project_ui_stack.md`` the dashboard never reads mock data, so the
tests don't either. Each test creates a real ScheduledResumeStore +
real audit JSONL + real workspace tree on tmp_path, builds the app,
and exercises endpoints via :class:`fastapi.testclient.TestClient`.
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
from selffork_orchestrator.resume.store import (
    ScheduledResume,
    ScheduledResumeStore,
)


def _build_test_client(tmp_path: Path) -> TestClient:
    config = DashboardConfig(
        audit_dir=tmp_path / "audit",
        resume_dir=tmp_path / "scheduled",
        projects_root=tmp_path / "projects",
        selffork_script=tmp_path / "fake-selffork",
    )
    config.audit_dir.mkdir(parents=True, exist_ok=True)
    config.resume_dir.mkdir(parents=True, exist_ok=True)
    config.projects_root.mkdir(parents=True, exist_ok=True)
    return TestClient(build_app(config))


def _seed_paused_record(
    tmp_path: Path,
    *,
    session_id: str = "01HJTESTSESSIONABCDEFGHIJK",
    resume_at: datetime | None = None,
    cli_agent: str = "claude-code",
    kind: str = "rpd",
    workspace_path: str | None = None,
) -> ScheduledResume:
    store = ScheduledResumeStore(root=tmp_path / "scheduled")
    rec = ScheduledResume(
        session_id=session_id,
        scheduled_at=datetime.now(UTC),
        resume_at=resume_at if resume_at is not None else datetime.now(UTC) + timedelta(hours=1),
        cli_agent=cli_agent,
        config_path=None,
        prd_path=str(tmp_path / "prd.md"),
        workspace_path=workspace_path or str(tmp_path / "ws" / session_id),
        reason="seeded by test",
        kind=kind,
    )
    store.save(rec)
    return rec


def _seed_audit_log(
    tmp_path: Path,
    *,
    session_id: str,
    states: list[str] | None = None,
    rounds: int = 0,
    cli_binary: str = "/opt/homebrew/bin/opencode",
) -> Path:
    """Write a realistic audit JSONL file matching production format."""
    audit_root = tmp_path / "audit"
    audit_root.mkdir(parents=True, exist_ok=True)
    path = audit_root / f"{session_id}.jsonl"
    base_ts = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    lines: list[dict[str, object]] = []

    def _emit(category: str, payload: dict[str, object], *, offset_s: int = 0) -> None:
        lines.append(
            {
                "ts": (base_ts + timedelta(seconds=offset_s + len(lines))).isoformat(),
                "correlation_id": "01HJTESTCORRELATIONABCDEF",
                "session_id": session_id,
                "category": category,
                "level": "INFO",
                "event": "test",
                "payload": payload,
            },
        )

    states = states or ["preparing", "running", "completed", "torn_down"]
    prev = "idle"
    for st in states:
        _emit("session.state", {"from": prev, "to": st})
        prev = st
    for i in range(rounds):
        _emit("agent.invoke", {"round": i, "binary": cli_binary, "args_count": 3})
        _emit("agent.output", {"round": i, "exit_code": 0, "output_chars": 42})

    path.write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n",
        encoding="utf-8",
    )
    return path


# ── /api/health ───────────────────────────────────────────────────────────────


class TestHealth:
    def test_returns_paths(self, tmp_path: Path) -> None:
        client = _build_test_client(tmp_path)
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["audit_dir"].endswith("audit")
        assert body["resume_dir"].endswith("scheduled")


# ── /api/sessions/paused ──────────────────────────────────────────────────────


class TestPausedListing:
    def test_empty_dir_returns_empty_array(self, tmp_path: Path) -> None:
        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/paused")
        assert r.status_code == 200
        assert r.json() == []

    def test_records_returned_with_is_due_flag(self, tmp_path: Path) -> None:
        # One record in the future, one in the past.
        _seed_paused_record(
            tmp_path,
            session_id="future",
            resume_at=datetime.now(UTC) + timedelta(hours=2),
        )
        _seed_paused_record(
            tmp_path,
            session_id="past",
            resume_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/paused")
        assert r.status_code == 200
        ids = {row["session_id"]: row["is_due"] for row in r.json()}
        assert ids == {"past": True, "future": False}


# ── /api/sessions/recent ──────────────────────────────────────────────────────


class TestRecentListing:
    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/recent")
        assert r.status_code == 200
        assert r.json() == []

    def test_summarises_real_audit_jsonl(self, tmp_path: Path) -> None:
        _seed_audit_log(
            tmp_path,
            session_id="01HJSESSIONONE",
            states=["preparing", "running", "completed", "torn_down"],
            rounds=3,
            cli_binary="/opt/homebrew/bin/opencode",
        )
        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/recent")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        row = rows[0]
        assert row["session_id"] == "01HJSESSIONONE"
        assert row["final_state"] == "torn_down"
        assert row["rounds_observed"] == 3
        assert row["cli_agent"] == "opencode"

    def test_paused_session_inferred_as_paused_rate_limit(self, tmp_path: Path) -> None:
        # Real production case: a session that paused on round 0 ends
        # in state ``paused_rate_limit`` after the runtime detector
        # fired. The recent listing should surface that state verbatim.
        _seed_audit_log(
            tmp_path,
            session_id="01HJPAUSED",
            states=["preparing", "running", "paused_rate_limit", "torn_down"],
            rounds=1,
            cli_binary="/Users/x/.local/bin/claude",
        )
        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/recent")
        assert r.status_code == 200
        row = next(row for row in r.json() if row["session_id"] == "01HJPAUSED")
        assert row["final_state"] == "torn_down"  # last state observed
        assert row["cli_agent"] == "claude-code"


# ── /api/sessions/<id>/events ─────────────────────────────────────────────────


class TestEvents:
    def test_returns_all_events_for_known_session(self, tmp_path: Path) -> None:
        _seed_audit_log(tmp_path, session_id="01HJEVENTS", rounds=2)
        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/01HJEVENTS/events")
        assert r.status_code == 200
        events = r.json()
        # 4 state transitions + 2 rounds * 2 events = 8 events total.
        assert len(events) == 8
        cats = [e["category"] for e in events]
        assert cats[0] == "session.state"
        assert "agent.invoke" in cats
        assert "agent.output" in cats

    def test_unknown_session_returns_404(self, tmp_path: Path) -> None:
        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/never-existed/events")
        assert r.status_code == 404


# ── /api/sessions/<id>/plan ───────────────────────────────────────────────────


class TestPlan:
    def test_returns_real_plan_json(self, tmp_path: Path) -> None:
        # Seed the paused record + a real plan.json on disk at the
        # workspace_path the record points to.
        rec = _seed_paused_record(tmp_path, session_id="01HJPLAN")
        plan_dir = Path(rec.workspace_path) / ".selffork"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "summary": "build hello.py",
                    "sub_tasks": [
                        {"id": "1", "title": "write add", "status": "done"},
                    ],
                },
            ),
            encoding="utf-8",
        )
        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/01HJPLAN/plan")
        assert r.status_code == 200
        body = r.json()
        assert body["schema_version"] == 1
        assert body["summary"] == "build hello.py"
        assert len(body["sub_tasks"]) == 1

    def test_no_paused_record_returns_404(self, tmp_path: Path) -> None:
        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/never-paused/plan")
        assert r.status_code == 404


# ── /api/sessions/<id>/workspace ──────────────────────────────────────────────


class TestWorkspace:
    def test_lists_real_workspace_tree(self, tmp_path: Path) -> None:
        rec = _seed_paused_record(tmp_path, session_id="01HJWS")
        ws = Path(rec.workspace_path)
        ws.mkdir(parents=True)
        (ws / "add.py").write_text("def add(a, b): return a + b\n")
        (ws / "test_add.py").write_text("import add\n")
        (ws / ".selffork").mkdir()
        (ws / ".selffork" / "plan.json").write_text("{}")
        # Pruned dir; must NOT appear in the listing.
        (ws / "__pycache__").mkdir()
        (ws / "__pycache__" / "stale.pyc").write_text("noise")

        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/01HJWS/workspace")
        assert r.status_code == 200
        rows = r.json()
        names = {row["path"] for row in rows}
        assert "add.py" in names
        assert "test_add.py" in names
        assert ".selffork" in names
        assert ".selffork/plan.json" in names
        assert all("__pycache__" not in p for p in names)

    def test_unknown_session_returns_404(self, tmp_path: Path) -> None:
        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/never-existed/workspace")
        assert r.status_code == 404


# ── /api/sessions/run + /resume ───────────────────────────────────────────────


class TestRunEndpoint:
    def test_missing_prd_returns_400(self, tmp_path: Path) -> None:
        client = _build_test_client(tmp_path)
        r = client.post(
            "/api/sessions/run",
            json={"prd_path": str(tmp_path / "no-such-file.md")},
        )
        assert r.status_code == 400
        assert "PRD" in r.json()["detail"]

    def test_unknown_session_resume_returns_404(self, tmp_path: Path) -> None:
        client = _build_test_client(tmp_path)
        r = client.post("/api/sessions/paused/never/resume")
        assert r.status_code == 404


# ── WebSocket stream ──────────────────────────────────────────────────────────


class TestWebSocketStream:
    def test_streams_existing_events_then_appended_ones(self, tmp_path: Path) -> None:
        # Seed an audit file with two events, then connect the WebSocket,
        # then append a third event — the WebSocket must surface all three.
        _seed_audit_log(
            tmp_path,
            session_id="01HJSTREAM",
            states=["preparing", "running"],  # two state events
            rounds=0,
        )
        client = _build_test_client(tmp_path)
        with client.websocket_connect("/api/sessions/01HJSTREAM/stream") as ws:
            # Phase 2 drain — receive initial events.
            first = json.loads(ws.receive_text())
            second = json.loads(ws.receive_text())
            assert first["category"] == "session.state"
            assert second["category"] == "session.state"

            # Append a third event to disk.
            audit_path = tmp_path / "audit" / "01HJSTREAM.jsonl"
            new_event = {
                "ts": datetime.now(UTC).isoformat(),
                "correlation_id": "x",
                "session_id": "01HJSTREAM",
                "category": "agent.invoke",
                "level": "INFO",
                "event": "test",
                "payload": {"round": 0, "binary": "/x/opencode", "args_count": 1},
            }
            with audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(new_event) + "\n")

            # Phase 3 tail — receive the new event.
            third = json.loads(ws.receive_text())
            assert third["category"] == "agent.invoke"
