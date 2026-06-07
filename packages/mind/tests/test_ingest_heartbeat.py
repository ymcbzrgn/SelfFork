"""Heartbeat audit.jsonl → T2 Episodic ingest tests (ADR-009 §5)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from selffork_mind.ingest.heartbeat import (
    HeartbeatIngester,
    IngestCheckpoint,
    audit_entry_to_note,
    collect_entries,
)
from selffork_mind.store.base import (
    GLOBAL_GROUP_ID,
    PoolScope,
    RetrieveConfig,
    StoreScope,
)
from selffork_mind.store.duckdb import DuckDBMindStore
from selffork_mind.store.pool import PoolResolver

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ── audit_entry_to_note (pure projection) ──────────────────────────────


def _entry(
    *,
    tick: int = 1,
    trigger: str = "idle",
    project_slug: str | None = "selffork",
    decision_action: str | None = "TASK_START",
    result_outcome: str | None = "ok",
    air_alert: str | None = None,
    legal_actions: list[str] | None = None,
    idempotency_key: str | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    return {
        "tick": tick,
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
        "trigger": trigger,
        "world_state": {
            "last_active_workspace": project_slug,
            "pause_active": False,
            "within_active_hours": True,
        },
        "legal_actions": legal_actions if legal_actions is not None else ["TASK_START", "WAIT"],
        "decision_action": decision_action,
        "decision_reasoning": "test reasoning",
        "result_outcome": result_outcome,
        "air_alert": air_alert,
        "idempotency_key": (
            idempotency_key or f"{tick}:{decision_action or 'noop'}:{project_slug or 'global'}"
        ),
    }


class TestAuditEntryToNote:
    def test_project_workspace_routes_to_project_group(self) -> None:
        note = audit_entry_to_note(_entry(project_slug="selffork", tick=42))
        assert note is not None
        assert note.tier == "episodic"
        assert note.kind == "observation"
        assert note.project_slug == "selffork"
        assert note.group_id == "p:selffork"
        assert note.session_id == "heartbeat-tick-42"
        assert note.source_pointer == "heartbeat:42"

    def test_missing_workspace_routes_to_global(self) -> None:
        note = audit_entry_to_note(_entry(project_slug=None, tick=7))
        assert note is not None
        assert note.project_slug is None
        assert note.group_id == GLOBAL_GROUP_ID

    def test_air_alert_boosts_importance(self) -> None:
        note = audit_entry_to_note(_entry(air_alert="panic-keyword"))
        assert note is not None
        assert note.importance == pytest.approx(1.5)

    def test_no_air_alert_default_importance(self) -> None:
        note = audit_entry_to_note(_entry(air_alert=None))
        assert note is not None
        assert note.importance == pytest.approx(1.0)

    def test_idempotency_key_used_as_content_hash(self) -> None:
        note = audit_entry_to_note(_entry(idempotency_key="42:TASK_START:selffork"))
        assert note is not None
        assert note.content_hash == "42:TASK_START:selffork"

    def test_missing_idempotency_key_falls_back_to_hash(self) -> None:
        e = _entry()
        del e["idempotency_key"]
        note = audit_entry_to_note(e)
        assert note is not None
        # Content hash is the md5 of the rendered content body.
        assert len(note.content_hash) == 32  # md5 hex digest length

    def test_invalid_tick_returns_none(self) -> None:
        e = _entry()
        e["tick"] = "not-an-int"
        assert audit_entry_to_note(e) is None

    def test_legal_actions_in_content(self) -> None:
        note = audit_entry_to_note(_entry(legal_actions=["TASK_START", "OPERATOR_ASK"]))
        assert note is not None
        assert "TASK_START" in note.content
        assert "OPERATOR_ASK" in note.content

    def test_decision_outcome_in_content(self) -> None:
        note = audit_entry_to_note(
            _entry(decision_action="KANBAN_SUGGEST", result_outcome="failed"),
        )
        assert note is not None
        assert "action=KANBAN_SUGGEST" in note.content
        assert "outcome=failed" in note.content

    def test_intent_contains_tick(self) -> None:
        note = audit_entry_to_note(_entry(tick=123))
        assert note is not None
        assert note.intent == "heartbeat tick 123"

    def test_invalid_timestamp_falls_back_to_now(self) -> None:
        note = audit_entry_to_note(_entry(timestamp="not-iso"))
        assert note is not None
        assert isinstance(note.valid_from, datetime)


class TestIngestCheckpoint:
    def test_roundtrip(self) -> None:
        cp = IngestCheckpoint(
            last_byte_offset=1234,
            last_tick=42,
            last_ingested_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        )
        restored = IngestCheckpoint.from_dict(cp.to_dict())
        assert restored.last_byte_offset == 1234
        assert restored.last_tick == 42
        assert restored.last_ingested_at == cp.last_ingested_at

    def test_default_empty(self) -> None:
        cp = IngestCheckpoint()
        assert cp.last_byte_offset == 0
        assert cp.last_tick is None
        assert cp.last_ingested_at is None

    def test_from_dict_handles_missing_fields(self) -> None:
        cp = IngestCheckpoint.from_dict({})
        assert cp.last_byte_offset == 0

    def test_from_dict_handles_malformed_timestamp(self) -> None:
        cp = IngestCheckpoint.from_dict(
            {"last_byte_offset": 0, "last_tick": 1, "last_ingested_at": "bogus"},
        )
        assert cp.last_ingested_at is None


# ── HeartbeatIngester end-to-end ───────────────────────────────────────


def _write_lines(path: Path, entries: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for e in entries:
            fp.write(json.dumps(e) + "\n")


def _append_lines(path: Path, entries: list[dict[str, object]]) -> None:
    with path.open("a", encoding="utf-8") as fp:
        for e in entries:
            fp.write(json.dumps(e) + "\n")


class TestHeartbeatIngesterBasic:
    async def test_empty_file_no_notes(self, tmp_path: Path) -> None:
        audit = tmp_path / "audit.jsonl"
        # File doesn't exist yet.
        store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
        await store.setup()
        try:
            ingester = HeartbeatIngester(
                audit_path=audit,
                store=store,
                project_slug="test",
            )
            report = await ingester.ingest_pending()
            assert report.lines_scanned == 0
            assert report.notes_written == 0
        finally:
            await store.teardown()

    async def test_single_entry_writes_one_note(self, tmp_path: Path) -> None:
        audit = tmp_path / "audit.jsonl"
        _write_lines(audit, [_entry(tick=1)])

        store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
        await store.setup()
        try:
            ingester = HeartbeatIngester(
                audit_path=audit,
                store=store,
                project_slug="selffork",
            )
            report = await ingester.ingest_pending()
            assert report.lines_scanned == 1
            assert report.notes_written == 1
            assert report.skipped_malformed == 0
            assert report.last_tick == 1
            # Verify the note landed via retrieve.
            hits = await store.retrieve(
                RetrieveConfig(scope=StoreScope(group_id="p:selffork")),
            )
            assert len(hits) == 1
            assert hits[0].note.intent == "heartbeat tick 1"
        finally:
            await store.teardown()

    async def test_multiple_entries_written(self, tmp_path: Path) -> None:
        audit = tmp_path / "audit.jsonl"
        _write_lines(audit, [_entry(tick=i) for i in range(1, 6)])

        store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
        await store.setup()
        try:
            ingester = HeartbeatIngester(
                audit_path=audit,
                store=store,
                project_slug="selffork",
            )
            report = await ingester.ingest_pending()
            assert report.lines_scanned == 5
            assert report.notes_written == 5
            assert report.last_tick == 5
        finally:
            await store.teardown()


class TestIdempotency:
    async def test_reingest_same_lines_no_duplicates(self, tmp_path: Path) -> None:
        audit = tmp_path / "audit.jsonl"
        _write_lines(audit, [_entry(tick=i) for i in range(3)])

        store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
        await store.setup()
        try:
            ingester = HeartbeatIngester(
                audit_path=audit,
                store=store,
                project_slug="selffork",
            )
            first = await ingester.ingest_pending()
            assert first.notes_written == 3

            # Reset checkpoint to simulate re-running on the same data.
            ingester.checkpoint_path.unlink()  # type: ignore[union-attr]
            second = await ingester.ingest_pending()
            assert second.notes_written == 3  # same UUID5 → upsert, no new rows

            hits = await store.retrieve(
                RetrieveConfig(scope=StoreScope(group_id="p:selffork")),
            )
            # 3 distinct notes, not 6 — UUID5 identity collapsed the upsert.
            assert len(hits) == 3
        finally:
            await store.teardown()

    async def test_checkpoint_advances_between_runs(self, tmp_path: Path) -> None:
        audit = tmp_path / "audit.jsonl"
        _write_lines(audit, [_entry(tick=1), _entry(tick=2)])

        store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
        await store.setup()
        try:
            ingester = HeartbeatIngester(
                audit_path=audit,
                store=store,
                project_slug="selffork",
            )
            first = await ingester.ingest_pending()
            assert first.notes_written == 2
            first_offset = first.new_offset

            # Append a new line; the checkpoint should advance only over it.
            _append_lines(audit, [_entry(tick=3)])
            second = await ingester.ingest_pending()
            assert second.lines_scanned == 1
            assert second.notes_written == 1
            assert second.new_offset > first_offset
        finally:
            await store.teardown()


class TestMalformedLines:
    async def test_malformed_json_skipped(self, tmp_path: Path) -> None:
        audit = tmp_path / "audit.jsonl"
        audit.parent.mkdir(parents=True, exist_ok=True)
        with audit.open("w", encoding="utf-8") as fp:
            fp.write(json.dumps(_entry(tick=1)) + "\n")
            fp.write("not json at all\n")
            fp.write(json.dumps(_entry(tick=2)) + "\n")

        store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
        await store.setup()
        try:
            ingester = HeartbeatIngester(
                audit_path=audit,
                store=store,
                project_slug="selffork",
            )
            report = await ingester.ingest_pending()
            assert report.lines_scanned == 3
            assert report.notes_written == 2
            assert report.skipped_malformed == 1
        finally:
            await store.teardown()

    async def test_empty_line_ignored(self, tmp_path: Path) -> None:
        audit = tmp_path / "audit.jsonl"
        audit.parent.mkdir(parents=True, exist_ok=True)
        with audit.open("w", encoding="utf-8") as fp:
            fp.write(json.dumps(_entry(tick=1)) + "\n")
            fp.write("\n")
            fp.write(json.dumps(_entry(tick=2)) + "\n")

        store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
        await store.setup()
        try:
            ingester = HeartbeatIngester(
                audit_path=audit,
                store=store,
                project_slug="selffork",
            )
            report = await ingester.ingest_pending()
            assert report.notes_written == 2
            # The empty line is scanned but doesn't increment malformed.
            assert report.skipped_malformed == 0
        finally:
            await store.teardown()


class TestDualPoolRouting:
    async def test_project_entries_to_project_pool(self, tmp_path: Path) -> None:
        audit = tmp_path / "audit.jsonl"
        _write_lines(audit, [_entry(tick=1, project_slug="proj-a")])

        resolver = PoolResolver(project_slug="proj-a", home=tmp_path, embedding_dim=8)
        await resolver.setup()
        try:
            assert resolver._project is not None
            project_store = resolver._project.notes
            ingester = HeartbeatIngester(
                audit_path=audit,
                store=project_store,
                project_slug="proj-a",
            )
            await ingester.ingest_pending()

            hits = await resolver.retrieve(
                pool_scope=PoolScope(project_slug="proj-a"),
                config=RetrieveConfig(),
            )
            assert any("tick=1" in h.note.content for h in hits)
        finally:
            await resolver.teardown()

    async def test_global_entries_to_global_pool(self, tmp_path: Path) -> None:
        audit = tmp_path / "audit.jsonl"
        _write_lines(audit, [_entry(tick=1, project_slug=None)])

        resolver = PoolResolver(project_slug="proj-a", home=tmp_path, embedding_dim=8)
        await resolver.setup()
        try:
            assert resolver._global is not None
            global_store = resolver._global.notes
            ingester = HeartbeatIngester(
                audit_path=audit,
                store=global_store,
                project_slug=None,
            )
            await ingester.ingest_pending()

            hits = await resolver.retrieve(
                pool_scope=PoolScope(include_global=True),
                config=RetrieveConfig(),
            )
            assert any("tick=1" in h.note.content for h in hits)

            # Verify it's NOT in the project pool.
            project_hits = await resolver.retrieve(
                pool_scope=PoolScope(project_slug="proj-a"),
                config=RetrieveConfig(),
            )
            assert not any("tick=1" in h.note.content for h in project_hits)
        finally:
            await resolver.teardown()


class TestTailFollow:
    async def test_run_picks_up_new_lines(self, tmp_path: Path) -> None:
        audit = tmp_path / "audit.jsonl"
        _write_lines(audit, [_entry(tick=1)])

        store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
        await store.setup()
        try:
            ingester = HeartbeatIngester(
                audit_path=audit,
                store=store,
                project_slug="selffork",
                poll_seconds=0.05,
            )
            task = asyncio.create_task(ingester.run())
            # Let the first poll process the existing line.
            await asyncio.sleep(0.15)
            _append_lines(audit, [_entry(tick=2), _entry(tick=3)])
            await asyncio.sleep(0.2)
            ingester.stop()
            await asyncio.wait_for(task, timeout=2.0)

            hits = await store.retrieve(
                RetrieveConfig(scope=StoreScope(group_id="p:selffork")),
            )
            ticks = sorted(int(h.note.session_id.split("-")[-1]) for h in hits if h.note.session_id)
            assert ticks == [1, 2, 3]
        finally:
            await store.teardown()

    async def test_stop_terminates_run(self, tmp_path: Path) -> None:
        audit = tmp_path / "audit.jsonl"
        _write_lines(audit, [_entry(tick=1)])

        store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
        await store.setup()
        try:
            ingester = HeartbeatIngester(
                audit_path=audit,
                store=store,
                project_slug="selffork",
                poll_seconds=10.0,  # high so we exercise the stop path
            )
            task = asyncio.create_task(ingester.run())
            await asyncio.sleep(0.05)
            ingester.stop()
            await asyncio.wait_for(task, timeout=1.0)
            assert task.done()
        finally:
            await store.teardown()


class TestConcurrencyLock:
    """audit-god finding #2 regression — ingest_pending must serialise."""

    async def test_concurrent_ingest_serialises(self, tmp_path: Path) -> None:
        audit = tmp_path / "audit.jsonl"
        _write_lines(audit, [_entry(tick=i) for i in range(5)])

        store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
        await store.setup()
        try:
            ingester = HeartbeatIngester(
                audit_path=audit,
                store=store,
                project_slug="selffork",
            )
            # Two concurrent ingest calls — the lock must serialise them so
            # each line is counted exactly once across both reports.
            r1, r2 = await asyncio.gather(
                ingester.ingest_pending(),
                ingester.ingest_pending(),
            )
            total_scanned = r1.lines_scanned + r2.lines_scanned
            assert total_scanned == 5  # never 10; lock prevented double-scan
            hits = await store.retrieve(
                RetrieveConfig(scope=StoreScope(group_id="p:selffork")),
            )
            assert len(hits) == 5
        finally:
            await store.teardown()


class TestCollectEntries:
    def test_skips_blank_and_malformed(self) -> None:
        lines = [
            json.dumps(_entry(tick=1)),
            "",
            "not json",
            json.dumps(_entry(tick=2)),
            "[]",  # not a dict — should also be skipped
        ]
        out = collect_entries(lines)
        assert len(out) == 2
        assert {e["tick"] for e in out} == {1, 2}


class TestPositiveValidation:
    def test_negative_poll_seconds_raises(self, tmp_path: Path) -> None:
        store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
        with pytest.raises(ValueError, match="poll_seconds must be positive"):
            HeartbeatIngester(
                audit_path=tmp_path / "audit.jsonl",
                store=store,
                poll_seconds=0,
            )

    def test_checkpoint_path_defaults_next_to_audit(self, tmp_path: Path) -> None:
        store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
        ingester = HeartbeatIngester(
            audit_path=tmp_path / "audit.jsonl",
            store=store,
        )
        assert ingester.checkpoint_path == tmp_path / "audit.ingest-checkpoint.json"
