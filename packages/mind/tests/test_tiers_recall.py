"""Tests for :mod:`selffork_mind.memory.tiers.recall`.

Real audit JSONL files on tmp_path — no mocks. Validates StoreScope
filtering, project-slug inference, mtime sort, multi-dir merge,
malformed-line tolerance, async tail, and date-range queries.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import anyio
import anyio.lowlevel
import pytest

from selffork_mind.memory.tiers import (
    RecallEvent,
    RecallReader,
)
from selffork_mind.memory.tiers.recall import _infer_project_slug
from selffork_mind.store.base import StoreScope


def _make_event(
    *,
    session_id: str,
    category: str,
    ts: datetime,
    event: str = "ev",
    level: str = "INFO",
    payload: dict[str, object] | None = None,
    correlation_id: str = "corr-1",
) -> dict[str, object]:
    return {
        "ts": ts.isoformat().replace("+00:00", "Z"),
        "correlation_id": correlation_id,
        "session_id": session_id,
        "category": category,
        "level": level,
        "event": event,
        "payload": payload or {},
    }


def _write_audit_file(
    path: Path,
    events: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


# ── list_sessions ──────────────────────────────────────────────────────────


def test_list_sessions_empty_dir(tmp_path: Path) -> None:
    reader = RecallReader(audit_dirs=[tmp_path])
    assert reader.list_sessions() == []


def test_list_sessions_nonexistent_dir() -> None:
    reader = RecallReader(audit_dirs=[Path("/nonexistent/x")])
    assert reader.list_sessions() == []


def test_list_sessions_skip_malformed_lines(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    audit.mkdir()
    sid = str(uuid4())
    path = audit / f"{sid}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        f.write("not-json\n")
        f.write(
            json.dumps(
                _make_event(
                    session_id=sid,
                    category="session.state",
                    ts=datetime.now(UTC),
                    payload={"to": "completed"},
                ),
            )
            + "\n",
        )
    reader = RecallReader(audit_dirs=[audit])
    sessions = reader.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].final_state == "completed"


def test_list_sessions_multi_dir_merge(tmp_path: Path) -> None:
    orphan = tmp_path / "audit"
    project = tmp_path / "projects" / "foo" / "audit"

    s1, s2, s3 = str(uuid4()), str(uuid4()), str(uuid4())
    base = datetime.now(UTC)

    _write_audit_file(
        orphan / f"{s1}.jsonl",
        [_make_event(session_id=s1, category="session.state", ts=base)],
    )
    _write_audit_file(
        project / f"{s2}.jsonl",
        [_make_event(session_id=s2, category="session.state", ts=base)],
    )
    _write_audit_file(
        orphan / f"{s3}.jsonl",
        [_make_event(session_id=s3, category="session.state", ts=base)],
    )

    reader = RecallReader(audit_dirs=[orphan, project])
    sessions = reader.list_sessions()
    by_id = {s.session_id: s for s in sessions}
    assert set(by_id) == {s1, s2, s3}
    assert by_id[s2].project_slug == "foo"
    assert by_id[s1].project_slug is None
    assert by_id[s3].project_slug is None


def test_list_sessions_mtime_sort(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    audit.mkdir()
    s_old, s_new = str(uuid4()), str(uuid4())
    p_old = audit / f"{s_old}.jsonl"
    p_new = audit / f"{s_new}.jsonl"
    base = datetime.now(UTC)
    p_old.write_text(
        json.dumps(_make_event(session_id=s_old, category="session.state", ts=base)) + "\n",
    )
    p_new.write_text(
        json.dumps(_make_event(session_id=s_new, category="session.state", ts=base)) + "\n",
    )
    os.utime(p_old, (1000, 1000))
    os.utime(p_new, (2000, 2000))

    reader = RecallReader(audit_dirs=[audit])
    sessions = reader.list_sessions()
    assert sessions[0].session_id == s_new


def test_list_sessions_scope_project(tmp_path: Path) -> None:
    audit_a = tmp_path / "projects" / "alpha" / "audit"
    audit_b = tmp_path / "projects" / "beta" / "audit"
    s_a, s_b = str(uuid4()), str(uuid4())
    base = datetime.now(UTC)
    _write_audit_file(
        audit_a / f"{s_a}.jsonl",
        [_make_event(session_id=s_a, category="session.state", ts=base)],
    )
    _write_audit_file(
        audit_b / f"{s_b}.jsonl",
        [_make_event(session_id=s_b, category="session.state", ts=base)],
    )
    reader = RecallReader(audit_dirs=[audit_a, audit_b])
    only_alpha = reader.list_sessions(scope=StoreScope(project_slug="alpha"))
    assert [s.session_id for s in only_alpha] == [s_a]


def test_list_sessions_scope_session_id(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    s1, s2 = str(uuid4()), str(uuid4())
    base = datetime.now(UTC)
    for sid in (s1, s2):
        _write_audit_file(
            audit / f"{sid}.jsonl",
            [_make_event(session_id=sid, category="session.state", ts=base)],
        )
    reader = RecallReader(audit_dirs=[audit])
    only_s1 = reader.list_sessions(scope=StoreScope(session_id=s1))
    assert [s.session_id for s in only_s1] == [s1]


def test_list_sessions_scope_cli_agent(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    s_claude, s_gemini = str(uuid4()), str(uuid4())
    base = datetime.now(UTC)
    _write_audit_file(
        audit / f"{s_claude}.jsonl",
        [
            _make_event(
                session_id=s_claude,
                category="agent.invoke",
                ts=base,
                payload={"binary": "/usr/local/bin/claude"},
            ),
        ],
    )
    _write_audit_file(
        audit / f"{s_gemini}.jsonl",
        [
            _make_event(
                session_id=s_gemini,
                category="agent.invoke",
                ts=base,
                payload={"binary": "/usr/local/bin/gemini"},
            ),
        ],
    )
    reader = RecallReader(audit_dirs=[audit])
    claudes = reader.list_sessions(scope=StoreScope(cli_agent="claude-code"))
    assert [s.session_id for s in claudes] == [s_claude]


def test_list_sessions_limit(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    base = datetime.now(UTC)
    for _ in range(5):
        sid = str(uuid4())
        _write_audit_file(
            audit / f"{sid}.jsonl",
            [_make_event(session_id=sid, category="session.state", ts=base)],
        )
    reader = RecallReader(audit_dirs=[audit])
    assert len(reader.list_sessions(limit=2)) == 2


def test_list_sessions_skip_summary_when_no_events(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    audit.mkdir()
    sid = str(uuid4())
    (audit / f"{sid}.jsonl").write_text("not-json\nalso-not-json\n")
    reader = RecallReader(audit_dirs=[audit])
    assert reader.list_sessions() == []


# ── get_session ────────────────────────────────────────────────────────────


def test_get_session_missing(tmp_path: Path) -> None:
    reader = RecallReader(audit_dirs=[tmp_path])
    assert reader.get_session("missing") is None


def test_get_session_present(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    sid = str(uuid4())
    _write_audit_file(
        audit / f"{sid}.jsonl",
        [
            _make_event(
                session_id=sid,
                category="session.state",
                ts=datetime.now(UTC),
                payload={"to": "completed"},
            ),
        ],
    )
    reader = RecallReader(audit_dirs=[audit])
    s = reader.get_session(sid)
    assert s is not None
    assert s.final_state == "completed"


def test_get_session_scope_excludes_other_project(tmp_path: Path) -> None:
    audit = tmp_path / "projects" / "alpha" / "audit"
    sid = str(uuid4())
    _write_audit_file(
        audit / f"{sid}.jsonl",
        [_make_event(session_id=sid, category="session.state", ts=datetime.now(UTC))],
    )
    reader = RecallReader(audit_dirs=[audit])
    assert reader.get_session(sid, scope=StoreScope(project_slug="beta")) is None
    found = reader.get_session(sid, scope=StoreScope(project_slug="alpha"))
    assert found is not None
    assert found.project_slug == "alpha"


# ── read_session_events ────────────────────────────────────────────────────


def test_read_session_events_missing(tmp_path: Path) -> None:
    reader = RecallReader(audit_dirs=[tmp_path])
    assert reader.read_session_events("absent") == []


def test_read_session_events_unicode(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    sid = str(uuid4())
    _write_audit_file(
        audit / f"{sid}.jsonl",
        [
            _make_event(
                session_id=sid,
                category="agent.event",
                ts=datetime.now(UTC),
                event="naber dünyâ",
                payload={"x": "şğç"},
            ),
        ],
    )
    reader = RecallReader(audit_dirs=[audit])
    events = reader.read_session_events(sid)
    assert events[0].event == "naber dünyâ"
    assert events[0].payload["x"] == "şğç"


def test_read_session_events_partial_jsonl(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    audit.mkdir()
    sid = str(uuid4())
    path = audit / f"{sid}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(_make_event(session_id=sid, category="session.state", ts=datetime.now(UTC)))
            + "\n",
        )
        f.write('{"ts":"2026-...partial')
    reader = RecallReader(audit_dirs=[audit])
    events = reader.read_session_events(sid)
    assert len(events) == 1


def test_read_session_events_records_audit_path_and_slug(tmp_path: Path) -> None:
    audit = tmp_path / "projects" / "alpha" / "audit"
    sid = str(uuid4())
    _write_audit_file(
        audit / f"{sid}.jsonl",
        [_make_event(session_id=sid, category="session.state", ts=datetime.now(UTC))],
    )
    reader = RecallReader(audit_dirs=[audit])
    events = reader.read_session_events(sid)
    assert events[0].audit_path == audit / f"{sid}.jsonl"
    assert events[0].project_slug == "alpha"


# ── query_events ───────────────────────────────────────────────────────────


def test_query_events_category_filter(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    sid = str(uuid4())
    base = datetime.now(UTC)
    _write_audit_file(
        audit / f"{sid}.jsonl",
        [
            _make_event(session_id=sid, category="session.state", ts=base),
            _make_event(
                session_id=sid,
                category="agent.invoke",
                ts=base + timedelta(seconds=1),
            ),
            _make_event(
                session_id=sid,
                category="agent.output",
                ts=base + timedelta(seconds=2),
            ),
        ],
    )
    reader = RecallReader(audit_dirs=[audit])
    invokes = list(reader.query_events(session_id=sid, category="agent.invoke"))
    assert len(invokes) == 1
    assert invokes[0].category == "agent.invoke"


def test_query_events_date_range_half_open(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    sid = str(uuid4())
    base = datetime.now(UTC)
    _write_audit_file(
        audit / f"{sid}.jsonl",
        [
            _make_event(
                session_id=sid,
                category="agent.event",
                ts=base + timedelta(seconds=i),
            )
            for i in range(5)
        ],
    )
    reader = RecallReader(audit_dirs=[audit])
    events = list(
        reader.query_events(
            session_id=sid,
            since=base + timedelta(seconds=2),
            until=base + timedelta(seconds=4),
        ),
    )
    assert len(events) == 2  # seconds 2 and 3 — interval is [since, until)


def test_query_events_combined_scope_filter(tmp_path: Path) -> None:
    a_audit = tmp_path / "projects" / "a" / "audit"
    b_audit = tmp_path / "projects" / "b" / "audit"
    sa, sb = str(uuid4()), str(uuid4())
    base = datetime.now(UTC)
    _write_audit_file(
        a_audit / f"{sa}.jsonl",
        [
            _make_event(
                session_id=sa,
                category="agent.invoke",
                ts=base,
                payload={"binary": "claude"},
            ),
        ],
    )
    _write_audit_file(
        b_audit / f"{sb}.jsonl",
        [
            _make_event(
                session_id=sb,
                category="agent.invoke",
                ts=base,
                payload={"binary": "gemini"},
            ),
        ],
    )
    reader = RecallReader(audit_dirs=[a_audit, b_audit])
    in_a = list(reader.query_events(scope=StoreScope(project_slug="a")))
    assert all(ev.project_slug == "a" for ev in in_a)
    assert all(ev.session_id == sa for ev in in_a)


def test_query_events_yields_lazily(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    sid = str(uuid4())
    _write_audit_file(
        audit / f"{sid}.jsonl",
        [_make_event(session_id=sid, category="agent.event", ts=datetime.now(UTC))],
    )
    reader = RecallReader(audit_dirs=[audit])
    iterator: Iterator[RecallEvent] = reader.query_events(session_id=sid)
    # Consuming nothing → no events yielded yet (it's a generator).
    assert hasattr(iterator, "__next__")
    first = next(iterator)
    assert first.category == "agent.event"


# ── infer helpers ──────────────────────────────────────────────────────────


def test_infer_project_slug_orphan_layout() -> None:
    assert _infer_project_slug(Path("/Users/x/.selffork/audit/abc.jsonl")) is None


def test_infer_project_slug_project_layout() -> None:
    assert (
        _infer_project_slug(
            Path("/Users/x/.selffork/projects/myproj/audit/abc.jsonl"),
        )
        == "myproj"
    )


def test_infer_project_slug_dotfile_segment() -> None:
    assert (
        _infer_project_slug(
            Path("/Users/x/.selffork/projects/.hidden/audit/abc.jsonl"),
        )
        is None
    )


def test_audit_dirs_property(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    reader = RecallReader(audit_dirs=[a, b])
    assert reader.audit_dirs == (a, b)


def test_cli_inference_codex(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    sid = str(uuid4())
    _write_audit_file(
        audit / f"{sid}.jsonl",
        [
            _make_event(
                session_id=sid,
                category="agent.invoke",
                ts=datetime.now(UTC),
                payload={"binary": "/x/codex"},
            ),
        ],
    )
    reader = RecallReader(audit_dirs=[audit])
    s = reader.get_session(sid)
    assert s is not None
    assert s.cli_agent == "codex"


# ── tail (async) ───────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_tail_session_events_drains_then_appends(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    audit.mkdir()
    sid = str(uuid4())
    path = audit / f"{sid}.jsonl"
    base = datetime.now(UTC)
    _write_audit_file(
        path,
        [_make_event(session_id=sid, category="agent.event", ts=base, event="first")],
    )

    reader = RecallReader(audit_dirs=[audit])
    received: list[RecallEvent] = []

    async def consumer() -> None:
        async for ev in reader.tail_session_events(sid, poll_interval_seconds=0.05):
            received.append(ev)
            if len(received) >= 2:
                return

    async with anyio.create_task_group() as tg:
        tg.start_soon(consumer)
        # Let the drain phase finish before we append.
        await anyio.sleep(0.2)
        with path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    _make_event(
                        session_id=sid,
                        category="agent.event",
                        ts=base + timedelta(seconds=1),
                        event="second",
                    ),
                )
                + "\n",
            )
        # consumer cancels itself by returning once it has 2 events;
        # the tail generator's open file handle is released as the
        # async generator exits.

    assert [ev.event for ev in received] == ["first", "second"]


@pytest.mark.anyio
async def test_tail_session_events_no_dirs_raises() -> None:
    reader = RecallReader(audit_dirs=[])
    sid = str(uuid4())
    with pytest.raises(ValueError, match="no audit dirs"):
        async for _ in reader.tail_session_events(sid):
            pytest.fail("should not yield")


@pytest.mark.anyio
async def test_tail_session_events_waits_for_late_file(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    audit.mkdir()
    sid = str(uuid4())
    path = audit / f"{sid}.jsonl"

    reader = RecallReader(audit_dirs=[audit])
    received: list[RecallEvent] = []

    async def consumer() -> None:
        async for ev in reader.tail_session_events(sid, poll_interval_seconds=0.05):
            received.append(ev)
            return

    async def producer() -> None:
        await anyio.sleep(0.15)
        _write_audit_file(
            path,
            [
                _make_event(
                    session_id=sid,
                    category="agent.event",
                    ts=datetime.now(UTC),
                    event="late",
                ),
            ],
        )

    async with anyio.create_task_group() as tg:
        tg.start_soon(consumer)
        tg.start_soon(producer)
        await anyio.lowlevel.checkpoint()

    # Yield once to let the consumer's final iteration drain.
    await anyio.lowlevel.checkpoint()
    assert received and received[0].event == "late"
