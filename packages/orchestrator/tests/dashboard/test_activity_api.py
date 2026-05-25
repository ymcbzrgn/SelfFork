"""Integration + unit tests for the S8 activity feed.

Two layers:

* ``TestActivityEndpoint`` — exercises ``GET /api/activity`` over a real
  ``build_app`` + TestClient, staging audit/heartbeat/activity artefacts on
  disk (no mocks; the no-mock rule means an idle system yields ``[]``).
* ``TestActivityAggregator`` — calls :func:`aggregate_activity` directly so
  the pure-function behaviour (correlation pairing, telegram ring, filters,
  cursor) is testable without standing up FastAPI.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from selffork_orchestrator.dashboard.activity import (
    aggregate_activity,
    append_dashboard_activity,
    default_activity_log_path,
    default_heartbeat_audit_path,
)
from selffork_orchestrator.dashboard.server import DashboardConfig, build_app
from selffork_orchestrator.dashboard.telegram_router import (
    TelegramActivityEntry,
    TelegramActivityResponse,
)
from selffork_orchestrator.heartbeat.audit import AuditEntry, AuditWriter

_BASE = datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC)


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


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _event(
    category: str,
    *,
    ts: datetime,
    payload: dict[str, object] | None = None,
    event: str = "event",
    session_id: str | None = None,
) -> dict[str, object]:
    return {
        "ts": _iso(ts),
        "correlation_id": None,
        "session_id": session_id,
        "category": category,
        "level": "INFO",
        "event": event,
        "payload": payload or {},
    }


def _write_session(audit_dir: Path, sid: str, events: list[dict[str, object]]) -> Path:
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / f"{sid}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    return path


# ── Endpoint ─────────────────────────────────────────────────────────────────


class TestActivityEndpoint:
    def test_empty_system_returns_empty_feed(self, tmp_path: Path) -> None:
        client, _ = _client(tmp_path)
        r = client.get("/api/activity")
        assert r.status_code == 200
        body = r.json()
        assert body == {"rows": [], "has_more": False}

    def test_session_bracket_and_tool_rows(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        _write_session(
            config.audit_dir,
            "01SESSIONAAAAAAAAAAAAAAAAA",
            [
                _event("session.state", ts=_BASE, payload={"to": "running"}),
                _event(
                    "tool.call",
                    ts=_BASE + timedelta(seconds=2),
                    payload={"tool": "kanban_card_move", "round": 0, "order": 0},
                ),
                _event(
                    "session.state",
                    ts=_BASE + timedelta(seconds=5),
                    payload={"to": "completed"},
                ),
            ],
        )
        r = client.get("/api/activity")
        assert r.status_code == 200
        kinds = [row["event_kind"] for row in r.json()["rows"]]
        assert "session_started" in kinds
        assert "session_ended" in kinds
        assert "tool_call" in kinds

    def test_structured_question_answer_pair_correlates(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        _write_session(
            config.audit_dir,
            "01SESSIONBBBBBBBBBBBBBBBBB",
            [
                _event(
                    "tool.structured_question",
                    ts=_BASE,
                    payload={"tool": "AskUserQuestion", "round": 1, "order": 0},
                ),
                _event(
                    "tool.structured_answer",
                    ts=_BASE + timedelta(seconds=1),
                    payload={"tool": "AskUserQuestion", "round": 1, "order": 0, "status": "ok"},
                ),
            ],
        )
        rows = client.get("/api/activity").json()["rows"]
        q = next(r for r in rows if r["event_kind"] == "tool.structured_question")
        a = next(r for r in rows if r["event_kind"] == "tool.structured_answer")
        assert q["correlation_id"] == a["correlation_id"]
        assert q["correlation_id"].endswith(":1:0")

    def test_destructive_confirm_rows(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        _write_session(
            config.audit_dir,
            "01SESSIONCCCCCCCCCCCCCCCCC",
            [
                _event(
                    "destructive_action_requested",
                    ts=_BASE,
                    payload={"command_summary": "rm -rf build", "action_id": "act-1"},
                ),
                _event(
                    "destructive_action_approved",
                    ts=_BASE + timedelta(seconds=3),
                    payload={"action_id": "act-1"},
                ),
            ],
        )
        rows = client.get("/api/activity").json()["rows"]
        req = next(
            r for r in rows if r["event_kind"] == "destructive_confirm_requested"
        )
        assert req["severity"] == "warn"
        assert "rm -rf build" in req["summary"]
        assert any(
            r["event_kind"] == "destructive_confirm_resolved" for r in rows
        )

    def test_heartbeat_tick_row(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        writer = AuditWriter(path=default_heartbeat_audit_path(config.audit_dir))
        writer.write(
            AuditEntry(
                tick=7,
                timestamp=_BASE,
                trigger="reconcile",
                world_state={"last_active_workspace": "calc"},
                legal_actions=["WAIT", "TASK_START"],
                decision_action="TASK_START",
                decision_reasoning="Backlog has a ready card.",
                result_action="TASK_START",
                result_outcome="started",
            ),
        )
        rows = client.get("/api/activity").json()["rows"]
        tick = next(r for r in rows if r["event_kind"] == "heartbeat_tick")
        assert "TASK_START" in tick["summary"]
        assert tick["intent"] == "Backlog has a ready card."
        assert tick["project_slug"] == "calc"

    def test_project_archive_mutation_appears(self, tmp_path: Path) -> None:
        client, _ = _client(tmp_path)
        client.post("/api/projects", json={"name": "Feed Demo"})
        client.post("/api/projects/feed-demo/archive")
        rows = client.get("/api/activity").json()["rows"]
        archived = [r for r in rows if r["event_kind"] == "project_archived"]
        assert len(archived) == 1
        assert archived[0]["project_slug"] == "feed-demo"

    def test_filter_by_event_kind(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        _write_session(
            config.audit_dir,
            "01SESSIONDDDDDDDDDDDDDDDDD",
            [
                _event("session.state", ts=_BASE, payload={"to": "running"}),
                _event(
                    "tool.call",
                    ts=_BASE + timedelta(seconds=1),
                    payload={"tool": "x", "round": 0, "order": 0},
                ),
            ],
        )
        rows = client.get("/api/activity", params={"event_kind": "tool_call"}).json()[
            "rows"
        ]
        assert rows
        assert all(r["event_kind"] == "tool_call" for r in rows)

    def test_limit_capped_at_200(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        # 250 heartbeat ticks → request limit=5000, expect ≤ 200 returned.
        writer = AuditWriter(path=default_heartbeat_audit_path(config.audit_dir))
        for i in range(250):
            writer.write(
                AuditEntry(
                    tick=i,
                    timestamp=_BASE + timedelta(seconds=i),
                    trigger="reconcile",
                ),
            )
        body = client.get("/api/activity", params={"limit": 5000}).json()
        assert len(body["rows"]) == 200
        assert body["has_more"] is True

    def test_rows_descending_by_ts(self, tmp_path: Path) -> None:
        client, config = _client(tmp_path)
        writer = AuditWriter(path=default_heartbeat_audit_path(config.audit_dir))
        for i in range(5):
            writer.write(
                AuditEntry(tick=i, timestamp=_BASE + timedelta(minutes=i), trigger="t"),
            )
        rows = client.get("/api/activity").json()["rows"]
        timestamps = [r["ts"] for r in rows]
        assert timestamps == sorted(timestamps, reverse=True)


# ── Pure aggregator ──────────────────────────────────────────────────────────


class TestActivityAggregator:
    def _paths(self, tmp_path: Path) -> dict[str, Path]:
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        return {
            "audit_dir": audit_dir,
            "projects_root": tmp_path / "projects",
            "heartbeat_audit_path": default_heartbeat_audit_path(audit_dir),
            "activity_log_path": default_activity_log_path(audit_dir),
        }

    def test_empty_returns_empty(self, tmp_path: Path) -> None:
        p = self._paths(tmp_path)
        rows, has_more = aggregate_activity(**p)
        assert rows == []
        assert has_more is False

    def test_telegram_ring_maps_both_directions(self, tmp_path: Path) -> None:
        p = self._paths(tmp_path)
        tg = TelegramActivityResponse(
            inbound=[
                TelegramActivityEntry(
                    at=_iso(_BASE),
                    direction="inbound",
                    summary="operator: status?",
                ),
            ],
            outbound=[
                TelegramActivityEntry(
                    at=_iso(_BASE + timedelta(seconds=1)),
                    direction="outbound",
                    summary="Self Jr: shipping",
                ),
            ],
        )
        rows, _ = aggregate_activity(**p, telegram_activity=tg)
        kinds = {r.event_kind for r in rows}
        assert kinds == {"telegram_inbound", "telegram_outbound"}

    def test_since_filters_older_rows(self, tmp_path: Path) -> None:
        p = self._paths(tmp_path)
        append_dashboard_activity(
            p["activity_log_path"],
            category="project_paused",
            summary="old",
            project_slug="a",
        )
        rows_all, _ = aggregate_activity(**p)
        assert len(rows_all) == 1
        # A future ``since`` excludes the just-written row.
        rows_future, _ = aggregate_activity(
            **p,
            since=datetime.now(UTC) + timedelta(hours=1),
        )
        assert rows_future == []

    def test_before_cursor_excludes_newer(self, tmp_path: Path) -> None:
        p = self._paths(tmp_path)
        _write_session(
            p["audit_dir"],
            "01SESSIONEEEEEEEEEEEEEEEEE",
            [
                _event(
                    "tool.call",
                    ts=_BASE,
                    payload={"tool": "old", "round": 0, "order": 0},
                ),
                _event(
                    "tool.call",
                    ts=_BASE + timedelta(hours=2),
                    payload={"tool": "new", "round": 1, "order": 0},
                ),
            ],
        )
        rows, _ = aggregate_activity(
            **p,
            before=_BASE + timedelta(hours=1),
        )
        tool_rows = [r for r in rows if r.event_kind == "tool_call"]
        assert len(tool_rows) == 1
        assert tool_rows[0].payload.get("tool") == "old"

    def test_project_filter(self, tmp_path: Path) -> None:
        p = self._paths(tmp_path)
        append_dashboard_activity(
            p["activity_log_path"],
            category="project_archived",
            summary="archived a",
            project_slug="alpha",
        )
        append_dashboard_activity(
            p["activity_log_path"],
            category="project_archived",
            summary="archived b",
            project_slug="beta",
        )
        rows, _ = aggregate_activity(**p, project_slug="alpha")
        assert len(rows) == 1
        assert rows[0].project_slug == "alpha"

    def test_seq_id_is_epoch_millis(self, tmp_path: Path) -> None:
        p = self._paths(tmp_path)
        append_dashboard_activity(
            p["activity_log_path"],
            category="project_resumed",
            summary="resumed",
            project_slug="x",
        )
        rows, _ = aggregate_activity(**p)
        assert rows[0].seq_id == int(rows[0].ts.timestamp() * 1000)

    def test_file_cap_truncation_flags_has_more(self, tmp_path: Path) -> None:
        # >120 session files → the scan truncates; has_more must signal the
        # window is incomplete even though limit is far from reached
        # (audit-god MAJOR #1 — silent drop otherwise).
        p = self._paths(tmp_path)
        for i in range(125):
            _write_session(
                p["audit_dir"],
                f"sess-{i:04d}",
                [
                    _event(
                        "tool.call",
                        ts=_BASE + timedelta(seconds=i),
                        payload={"tool": "x", "round": 0, "order": 0},
                    ),
                ],
            )
        _rows, has_more = aggregate_activity(**p, limit=500)
        assert has_more is True

    def test_event_kind_filter_excludes_other_sources(self, tmp_path: Path) -> None:
        # A kind-filtered request returns only that kind even when other
        # sources have data (the short-circuit must not change output).
        p = self._paths(tmp_path)
        AuditWriter(path=p["heartbeat_audit_path"]).write(
            AuditEntry(tick=1, timestamp=_BASE, trigger="reconcile"),
        )
        append_dashboard_activity(
            p["activity_log_path"],
            category="project_archived",
            summary="archived",
            project_slug="a",
        )
        rows, _ = aggregate_activity(**p, event_kind="project_archived")
        assert rows
        assert all(r.event_kind == "project_archived" for r in rows)
