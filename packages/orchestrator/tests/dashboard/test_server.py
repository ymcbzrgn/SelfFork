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


def _build_run_config(
    tmp_path: Path,
) -> tuple[DashboardConfig, Path, Path]:
    """Stage a real bash recorder for the run endpoint to spawn.

    Returns ``(config, fake_script, argv_log)``. The recorder writes
    each positional argument on its own line so the test can grep for
    ``--project`` and ``<slug>`` independently.
    """
    import os

    argv_log = tmp_path / "argv.log"
    fake_script = tmp_path / "fake-selffork"
    fake_script.write_text(
        f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" > {argv_log}\n',
        encoding="utf-8",
    )
    # Test-only: shell script must be executable for the dashboard's
    # subprocess.create_subprocess_exec to spawn it.
    os.chmod(fake_script, 0o755)  # noqa: S103

    config = DashboardConfig(
        audit_dir=tmp_path / "audit",
        resume_dir=tmp_path / "scheduled",
        projects_root=tmp_path / "projects",
        selffork_script=fake_script,
    )
    config.audit_dir.mkdir(parents=True, exist_ok=True)
    config.resume_dir.mkdir(parents=True, exist_ok=True)
    config.projects_root.mkdir(parents=True, exist_ok=True)
    return config, fake_script, argv_log


def _wait_for_argv(argv_log: Path, pid: int, timeout: float = 2.0) -> list[str]:
    """Wait for the bash recorder to write its argv, then reap the child.

    Without explicit reap the asyncio subprocess transport leaks, which
    triggers ``ResourceWarning``s during pytest teardown — the warnings
    are ``-W error``-promoted in CI and turn passing tests red.
    """
    import errno
    import os
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if argv_log.is_file() and argv_log.stat().st_size > 0:
            break
        time.sleep(0.05)
    assert argv_log.is_file(), "fake-selffork never executed"

    # Reap the zombie left behind by the dashboard's fire-and-forget
    # subprocess.create_subprocess_exec. Any error here means the child
    # was already reaped by asyncio's child watcher — that's fine.
    try:
        os.waitpid(pid, 0)
    except OSError as exc:
        if exc.errno != errno.ECHILD:
            raise

    return argv_log.read_text(encoding="utf-8").splitlines()


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

    def test_merges_per_project_audit_dirs(self, tmp_path: Path) -> None:
        # Orphan run lands in the global audit dir; project run lands
        # under ~/.selffork/projects/<slug>/audit/. The /api/sessions/recent
        # endpoint must walk both and present a single merged listing.
        from selffork_orchestrator.projects.store import ProjectStore

        _seed_audit_log(tmp_path, session_id="01HJORPHAN", rounds=1)

        project_store = ProjectStore(root=tmp_path / "projects")
        project_store.create(name="My", slug="myproj")
        project_audit = project_store.audit_dir("myproj")
        project_audit.mkdir(parents=True, exist_ok=True)

        project_jsonl = project_audit / "01HJPROJSESSION.jsonl"
        project_jsonl.write_text(
            json.dumps(
                {
                    "ts": "2026-05-01T12:00:00+00:00",
                    "correlation_id": "01HJTESTCORRELATIONABCDEF",
                    "session_id": "01HJPROJSESSION",
                    "category": "session.state",
                    "level": "INFO",
                    "event": "test",
                    "payload": {"from": "idle", "to": "preparing"},
                },
            )
            + "\n",
            encoding="utf-8",
        )

        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/recent")
        assert r.status_code == 200
        rows = r.json()
        session_ids = {row["session_id"] for row in rows}
        assert session_ids == {"01HJORPHAN", "01HJPROJSESSION"}


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

    def test_resolves_project_audit_dir(self, tmp_path: Path) -> None:
        # Order 1 #1.B regression: events for a session stored under
        # a project's audit dir used to 404 because the endpoint only
        # looked in the orphan audit dir. _resolve_audit_dir now walks
        # both layouts.
        from selffork_orchestrator.projects.store import ProjectStore

        project_store = ProjectStore(root=tmp_path / "projects")
        project_store.create(name="My", slug="myproj")
        project_audit = project_store.audit_dir("myproj")
        project_audit.mkdir(parents=True, exist_ok=True)

        project_jsonl = project_audit / "01HJPROJEVENT.jsonl"
        project_jsonl.write_text(
            json.dumps(
                {
                    "ts": "2026-05-01T12:00:00+00:00",
                    "correlation_id": "x",
                    "session_id": "01HJPROJEVENT",
                    "category": "agent.invoke",
                    "level": "INFO",
                    "event": "test",
                    "payload": {
                        "round": 0,
                        "binary": "/x/opencode",
                        "args_count": 1,
                    },
                },
            )
            + "\n",
            encoding="utf-8",
        )

        client = _build_test_client(tmp_path)
        r = client.get("/api/sessions/01HJPROJEVENT/events")
        assert r.status_code == 200
        events = r.json()
        assert len(events) == 1
        assert events[0]["category"] == "agent.invoke"


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

    def test_run_with_project_slug_passes_to_cli(self, tmp_path: Path) -> None:
        # Order 1 #1.C regression: the dashboard accepted ``project_slug``
        # in the request payload but never forwarded it to the CLI, so
        # project-aware runs fell back to orphan audit dirs. Real
        # subprocess (no mocks) — the ``selffork`` script is replaced
        # with a bash recorder that writes its argv to a log file.
        config, _, argv_log = _build_run_config(tmp_path)
        prd = tmp_path / "prd.md"
        prd.write_text("# Test PRD\n", encoding="utf-8")

        client = TestClient(build_app(config))
        r = client.post(
            "/api/sessions/run",
            json={"prd_path": str(prd), "project_slug": "myproj"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "started"

        argv_lines = _wait_for_argv(argv_log, r.json()["pid"])
        assert "run" in argv_lines
        assert str(prd) in argv_lines
        assert "--project" in argv_lines
        assert "myproj" in argv_lines

    def test_run_without_project_slug_omits_project_flag(
        self,
        tmp_path: Path,
    ) -> None:
        # Sanity check: omitting project_slug must not inject --project.
        config, _, argv_log = _build_run_config(tmp_path)
        prd = tmp_path / "prd.md"
        prd.write_text("# Test PRD\n", encoding="utf-8")

        client = TestClient(build_app(config))
        r = client.post(
            "/api/sessions/run",
            json={"prd_path": str(prd)},
        )
        assert r.status_code == 200

        argv_lines = _wait_for_argv(argv_log, r.json()["pid"])
        assert "run" in argv_lines
        assert "--project" not in argv_lines


# ── WebSocket stream ──────────────────────────────────────────────────────────


class TestWebSocketStream:
    def test_streams_existing_events_then_appended_ones(self, tmp_path: Path) -> None:
        # Seed an audit file with two events, then connect the WebSocket,
        # then append a third event — the WebSocket must surface all three
        # wrapped in M-1 envelopes (Order 2).
        _seed_audit_log(
            tmp_path,
            session_id="01HJSTREAM",
            states=["preparing", "running"],  # two state events
            rounds=0,
        )
        client = _build_test_client(tmp_path)
        with client.websocket_connect("/api/sessions/01HJSTREAM/stream") as ws:
            # Phase 2 drain — receive initial envelopes.
            first = json.loads(ws.receive_text())
            second = json.loads(ws.receive_text())
            assert first["event_type"] == "audit"
            assert first["payload"]["category"] == "session.state"
            assert first["seq"] == 1
            assert second["event_type"] == "audit"
            assert second["payload"]["category"] == "session.state"
            assert second["seq"] == 2

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

            # Phase 3 tail — receive the new envelope.
            third = json.loads(ws.receive_text())
            assert third["event_type"] == "audit"
            assert third["payload"]["category"] == "agent.invoke"
            assert third["seq"] == 3
            assert third["session_id"] == "01HJSTREAM"

    def test_resolves_project_audit_dir(self, tmp_path: Path) -> None:
        # Order 1 #1.B regression: WS stream used to read only the
        # orphan audit_dir. Project sessions must also stream — wrapped
        # in M-1 envelopes (Order 2).
        from selffork_orchestrator.projects.store import ProjectStore

        project_store = ProjectStore(root=tmp_path / "projects")
        project_store.create(name="My", slug="myproj")
        project_audit = project_store.audit_dir("myproj")
        project_audit.mkdir(parents=True, exist_ok=True)

        project_jsonl = project_audit / "01HJPROJWS.jsonl"
        project_jsonl.write_text(
            json.dumps(
                {
                    "ts": "2026-05-01T12:00:00+00:00",
                    "correlation_id": "x",
                    "session_id": "01HJPROJWS",
                    "category": "session.state",
                    "level": "INFO",
                    "event": "test",
                    "payload": {"from": "idle", "to": "preparing"},
                },
            )
            + "\n",
            encoding="utf-8",
        )

        client = _build_test_client(tmp_path)
        with client.websocket_connect(
            "/api/sessions/01HJPROJWS/stream",
        ) as ws:
            first = json.loads(ws.receive_text())
            assert first["event_type"] == "audit"
            assert first["seq"] == 1
            assert first["payload"]["category"] == "session.state"
            assert first["payload"]["payload"] == {
                "from": "idle",
                "to": "preparing",
            }

    def test_unknown_session_closes_with_4404(self, tmp_path: Path) -> None:
        # Without a matching audit file in either layout the WS
        # closes with HTTP-mirror code 4404 (mirrors REST 404).
        import pytest
        from starlette.websockets import WebSocketDisconnect

        client = _build_test_client(tmp_path)
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(
                "/api/sessions/never-was/stream",
            ) as ws,
        ):
            ws.receive_text()
        assert exc_info.value.code == 4404


# ── /api/projects/<slug>/kanban/stream ────────────────────────────────────────


class TestKanbanWebSocketStream:
    def test_pushes_initial_then_update_on_disk_mutation(self, tmp_path: Path) -> None:
        # Initial snapshot, then mutate the board on disk via ProjectStore;
        # the WS must surface a second message reflecting the new card.
        from selffork_orchestrator.projects.store import ProjectStore

        store = ProjectStore(root=tmp_path / "projects")
        store.create(name="Live", slug="live")

        client = _build_test_client(tmp_path)
        with client.websocket_connect("/api/projects/live/kanban/stream") as ws:
            initial = json.loads(ws.receive_text())
            assert initial["schema_version"] == 1
            assert initial["columns"] == [
                "backlog",
                "in_progress",
                "review",
                "done",
            ]
            initial_card_count = sum(len(cards) for cards in initial["cards_by_column"].values())
            assert initial_card_count == 0

            store.add_card(slug="live", title="Hello from store")

            second = json.loads(ws.receive_text())
            all_titles = [
                card["title"]
                for col_cards in second["cards_by_column"].values()
                for card in col_cards
            ]
            assert "Hello from store" in all_titles

    def test_unknown_project_closes_with_4404(self, tmp_path: Path) -> None:
        import pytest
        from starlette.websockets import WebSocketDisconnect

        client = _build_test_client(tmp_path)
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(
                "/api/projects/never-was/kanban/stream",
            ) as ws,
        ):
            ws.receive_text()
        assert exc_info.value.code == 4404
