"""Corrections.jsonl → T2 ingest tests (S-Bridge coaching loop)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from selffork_mind.ingest.heartbeat import (
    CorrectionIngester,
    correction_entry_to_note,
)
from selffork_mind.store.base import (
    GLOBAL_GROUP_ID,
    RetrieveConfig,
    StoreScope,
)
from selffork_mind.store.duckdb import DuckDBMindStore

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _row(
    *,
    key: str = "AUDIT-001",
    text: str = "should have rolled back",
    suggested: str | None = None,
    source: str = "operator-telegram",
    corrected_at: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "audit_idempotency_key": key,
        "correction_text": text,
        "source": source,
        "corrected_at": (corrected_at or datetime.now(UTC).isoformat()),
    }
    if suggested is not None:
        row["suggested_action"] = suggested
    return row


# ── correction_entry_to_note (pure projection) ─────────────────────────


class TestCorrectionEntryToNote:
    def test_basic_row_projects_to_decision_note(self) -> None:
        note = correction_entry_to_note(_row())
        assert note is not None
        assert note.tier == "episodic"
        assert note.kind == "decision"
        assert note.project_slug is None
        assert note.group_id == GLOBAL_GROUP_ID
        assert note.session_id == "correction-AUDIT-001"
        assert note.source_pointer == "correction:AUDIT-001"
        assert note.importance == 2.0
        assert "correction[AUDIT-001]" in note.content
        assert "should have rolled back" in note.content
        assert "source=operator-telegram" in note.content

    def test_suggested_action_appears_in_content(self) -> None:
        note = correction_entry_to_note(
            _row(suggested="git reset --soft HEAD~1"),
        )
        assert note is not None
        assert "suggested=git reset --soft HEAD~1" in note.content

    def test_content_hash_unique_per_corrected_at(self) -> None:
        when1 = datetime.now(UTC).isoformat()
        when2 = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
        n1 = correction_entry_to_note(_row(corrected_at=when1))
        n2 = correction_entry_to_note(_row(corrected_at=when2))
        assert n1 is not None and n2 is not None
        assert n1.content_hash != n2.content_hash

    def test_same_corrected_at_yields_same_hash(self) -> None:
        when = datetime.now(UTC).isoformat()
        n1 = correction_entry_to_note(_row(corrected_at=when))
        n2 = correction_entry_to_note(_row(corrected_at=when))
        assert n1 is not None and n2 is not None
        assert n1.content_hash == n2.content_hash

    def test_missing_key_returns_none(self) -> None:
        row = _row()
        del row["audit_idempotency_key"]
        assert correction_entry_to_note(row) is None

    def test_empty_key_returns_none(self) -> None:
        assert correction_entry_to_note(_row(key="")) is None

    def test_missing_text_returns_none(self) -> None:
        row = _row()
        del row["correction_text"]
        assert correction_entry_to_note(row) is None

    def test_whitespace_only_text_returns_none(self) -> None:
        assert correction_entry_to_note(_row(text="   ")) is None

    def test_invalid_corrected_at_falls_back_to_now(self) -> None:
        note = correction_entry_to_note(
            _row(corrected_at="not-an-iso-string"),
        )
        assert note is not None
        # valid_from is non-None and roughly "now".
        assert note.valid_from is not None
        delta = abs(
            (datetime.now(UTC) - note.valid_from).total_seconds(),
        )
        assert delta < 5.0

    def test_source_defaults_when_missing(self) -> None:
        row = _row()
        del row["source"]
        note = correction_entry_to_note(row)
        assert note is not None
        assert "source=operator" in note.content


# ── CorrectionIngester lifecycle ───────────────────────────────────────


@pytest.mark.anyio
async def test_ingester_empty_file_no_op(tmp_path: Path) -> None:
    store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
    await store.setup()
    try:
        ingester = CorrectionIngester(
            corrections_path=tmp_path / "corrections.jsonl",
            store=store,
        )
        report = await ingester.ingest_pending()
        assert report.lines_scanned == 0
        assert report.notes_written == 0
    finally:
        await store.teardown()


@pytest.mark.anyio
async def test_ingester_writes_correction_to_global_pool(
    tmp_path: Path,
) -> None:
    store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
    await store.setup()
    try:
        corrections = tmp_path / "corrections.jsonl"
        corrections.write_text(
            json.dumps(_row(key="AUD-1", text="prefer git revert")) + "\n",
            encoding="utf-8",
        )
        ingester = CorrectionIngester(
            corrections_path=corrections,
            store=store,
        )
        report = await ingester.ingest_pending()
        assert report.lines_scanned == 1
        assert report.notes_written == 1
        assert report.skipped_malformed == 0
        hits = await store.retrieve(
            RetrieveConfig(scope=StoreScope(group_id=GLOBAL_GROUP_ID)),
        )
        contents = [h.note.content for h in hits]
        assert any("prefer git revert" in c for c in contents)
    finally:
        await store.teardown()


@pytest.mark.anyio
async def test_ingester_routes_to_project_pool_when_slug_set(
    tmp_path: Path,
) -> None:
    store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
    await store.setup()
    try:
        corrections = tmp_path / "corrections.jsonl"
        corrections.write_text(
            json.dumps(_row(key="AUD-2", text="for project route")) + "\n",
            encoding="utf-8",
        )
        ingester = CorrectionIngester(
            corrections_path=corrections,
            store=store,
            project_slug="selffork",
        )
        await ingester.ingest_pending()
        hits = await store.retrieve(
            RetrieveConfig(scope=StoreScope(group_id="p:selffork")),
        )
        contents = [h.note.content for h in hits]
        assert any("for project route" in c for c in contents)
    finally:
        await store.teardown()


@pytest.mark.anyio
async def test_ingester_skips_malformed_lines(tmp_path: Path) -> None:
    store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
    await store.setup()
    try:
        corrections = tmp_path / "corrections.jsonl"
        corrections.write_text(
            "not-json\n"
            + json.dumps(_row(key="AUD-3", text="valid"))
            + "\n"
            + json.dumps({"wrong": "schema"})
            + "\n"
            + json.dumps([1, 2, 3])
            + "\n"
            + "\n",
            encoding="utf-8",
        )
        ingester = CorrectionIngester(
            corrections_path=corrections,
            store=store,
        )
        report = await ingester.ingest_pending()
        assert report.lines_scanned == 5  # incl. blank line
        assert report.notes_written == 1
        assert report.skipped_malformed == 3
    finally:
        await store.teardown()


@pytest.mark.anyio
async def test_ingester_checkpoint_persisted_across_runs(
    tmp_path: Path,
) -> None:
    store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
    await store.setup()
    try:
        corrections = tmp_path / "corrections.jsonl"
        corrections.write_text(
            json.dumps(_row(key="AUD-4", text="first")) + "\n",
            encoding="utf-8",
        )
        ingester = CorrectionIngester(
            corrections_path=corrections,
            store=store,
        )
        report1 = await ingester.ingest_pending()
        assert report1.notes_written == 1
        # Second run with no new content → no work.
        report2 = await ingester.ingest_pending()
        assert report2.lines_scanned == 0
        assert report2.notes_written == 0
        # Append another row → only that picked up.
        with corrections.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(_row(key="AUD-5", text="second")) + "\n")
        report3 = await ingester.ingest_pending()
        assert report3.lines_scanned == 1
        assert report3.notes_written == 1
    finally:
        await store.teardown()


@pytest.mark.anyio
async def test_ingester_idempotent_re_ingest_same_file(
    tmp_path: Path,
) -> None:
    """Re-running the ingester on a fresh checkpoint MUST collapse to upsert."""
    store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
    await store.setup()
    try:
        corrections = tmp_path / "corrections.jsonl"
        when = datetime.now(UTC).isoformat()
        corrections.write_text(
            json.dumps(_row(key="AUD-6", text="once", corrected_at=when)) + "\n",
            encoding="utf-8",
        )
        ckpt_a = tmp_path / "ckpt-a.json"
        i1 = CorrectionIngester(
            corrections_path=corrections,
            store=store,
            checkpoint_path=ckpt_a,
        )
        r1 = await i1.ingest_pending()
        # Fresh checkpoint path so second ingester re-reads the file.
        ckpt_b = tmp_path / "ckpt-b.json"
        i2 = CorrectionIngester(
            corrections_path=corrections,
            store=store,
            checkpoint_path=ckpt_b,
        )
        r2 = await i2.ingest_pending()
        assert r1.notes_written == 1
        assert r2.notes_written == 1
        hits = await store.retrieve(
            RetrieveConfig(scope=StoreScope(group_id=GLOBAL_GROUP_ID)),
        )
        # Same content_hash → single Note despite two ingests.
        matching = [h for h in hits if "AUD-6" in h.note.content]
        assert len(matching) == 1
    finally:
        await store.teardown()


@pytest.mark.anyio
async def test_ingester_run_loop_exits_on_stop(tmp_path: Path) -> None:
    store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
    await store.setup()
    try:
        ingester = CorrectionIngester(
            corrections_path=tmp_path / "corrections.jsonl",
            store=store,
            poll_seconds=0.05,
        )
        task = asyncio.create_task(ingester.run())
        await asyncio.sleep(0.15)
        ingester.stop()
        await asyncio.wait_for(task, timeout=1.0)
    finally:
        await store.teardown()


def test_negative_poll_seconds_raises(tmp_path: Path) -> None:
    store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
    with pytest.raises(ValueError, match="poll_seconds must be positive"):
        CorrectionIngester(
            corrections_path=tmp_path / "corrections.jsonl",
            store=store,
            poll_seconds=0,
        )


def test_checkpoint_path_defaults_next_to_corrections(tmp_path: Path) -> None:
    store = DuckDBMindStore(db_path=tmp_path / "notes.duckdb")
    ingester = CorrectionIngester(
        corrections_path=tmp_path / "corrections.jsonl",
        store=store,
    )
    assert ingester.checkpoint_path == (tmp_path / "corrections.ingest-checkpoint.json")
