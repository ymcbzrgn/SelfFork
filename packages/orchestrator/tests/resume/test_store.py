"""Unit tests for :class:`ScheduledResumeStore`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from selffork_orchestrator.resume.store import (
    ScheduledResume,
    ScheduledResumeStore,
)
from selffork_shared.errors import SelfForkError


def _record(
    *,
    session_id: str = "01HJTESTSESSIONABCDEFGHIJK",
    resume_at: datetime | None = None,
    cli_agent: str = "claude-code",
    kind: str = "rpd",
) -> ScheduledResume:
    return ScheduledResume(
        session_id=session_id,
        scheduled_at=datetime.now(UTC),
        resume_at=resume_at if resume_at is not None else datetime.now(UTC) + timedelta(hours=1),
        cli_agent=cli_agent,
        config_path=None,
        prd_path="/tmp/prd.md",  # noqa: S108 — fixture path
        workspace_path="/tmp/ws",  # noqa: S108
        reason="test",
        kind=kind,
    )


class TestRoundTrip:
    def test_save_load_returns_equal_record(self, tmp_path: Path) -> None:
        store = ScheduledResumeStore(root=tmp_path)
        original = _record()
        store.save(original)
        loaded = store.load(original.session_id)
        assert loaded is not None
        # Datetimes round-trip via ISO string with UTC normalization;
        # resulting tzinfo is exactly UTC.
        assert loaded.session_id == original.session_id
        assert loaded.resume_at == original.resume_at
        assert loaded.cli_agent == original.cli_agent
        assert loaded.kind == original.kind

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        store = ScheduledResumeStore(root=tmp_path)
        assert store.load("nonexistent") is None


class TestRemove:
    def test_remove_existing_returns_true(self, tmp_path: Path) -> None:
        store = ScheduledResumeStore(root=tmp_path)
        rec = _record()
        store.save(rec)
        assert store.remove(rec.session_id) is True
        assert store.load(rec.session_id) is None

    def test_remove_missing_returns_false(self, tmp_path: Path) -> None:
        store = ScheduledResumeStore(root=tmp_path)
        assert store.remove("nope") is False


class TestListing:
    def test_list_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        store = ScheduledResumeStore(root=tmp_path)
        assert store.list_all() == []

    def test_list_all_sorts_by_resume_at(self, tmp_path: Path) -> None:
        store = ScheduledResumeStore(root=tmp_path)
        now = datetime.now(UTC)
        far = _record(session_id="far", resume_at=now + timedelta(hours=5))
        near = _record(session_id="near", resume_at=now + timedelta(minutes=1))
        store.save(far)
        store.save(near)
        ids = [r.session_id for r in store.list_all()]
        assert ids == ["near", "far"]

    def test_list_due_filters_to_past(self, tmp_path: Path) -> None:
        store = ScheduledResumeStore(root=tmp_path)
        now = datetime.now(UTC)
        store.save(_record(session_id="past", resume_at=now - timedelta(seconds=1)))
        store.save(_record(session_id="future", resume_at=now + timedelta(hours=1)))
        due = store.list_due()
        assert [r.session_id for r in due] == ["past"]

    def test_corrupted_file_is_skipped(self, tmp_path: Path) -> None:
        store = ScheduledResumeStore(root=tmp_path)
        # Save one valid record.
        store.save(_record(session_id="ok"))
        # Drop a malformed file alongside it.
        (tmp_path / "broken.json").write_text("not json", encoding="utf-8")
        # Listing must not crash; we only get the valid one back.
        ids = [r.session_id for r in store.list_all()]
        assert ids == ["ok"]


class TestAtomicity:
    def test_save_replaces_atomically(self, tmp_path: Path) -> None:
        # Simulate two saves of the same session_id; the latest wins
        # and the file always contains a complete document.
        store = ScheduledResumeStore(root=tmp_path)
        store.save(_record(kind="rpm"))
        store.save(_record(kind="weekly"))
        loaded = store.load("01HJTESTSESSIONABCDEFGHIJK")
        assert loaded is not None
        assert loaded.kind == "weekly"
        # No leftover .tmp files.
        leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".")]
        assert leftovers == []


class TestIsDue:
    def test_past_resume_at_is_due(self) -> None:
        rec = _record(resume_at=datetime.now(UTC) - timedelta(seconds=1))
        assert rec.is_due() is True

    def test_future_resume_at_is_not_due(self) -> None:
        rec = _record(resume_at=datetime.now(UTC) + timedelta(hours=1))
        assert rec.is_due() is False


class TestFromJsonDict:
    def test_naive_datetime_raises(self) -> None:
        # A persisted record without a timezone marker is malformed —
        # must not silently default to local TZ (we'd schedule wrong).
        with pytest.raises(SelfForkError):
            ScheduledResume.from_json_dict(
                {
                    "session_id": "x",
                    "scheduled_at": "2026-05-01T14:00:00",  # naive
                    "resume_at": "2026-05-01T19:00:00",
                    "cli_agent": "claude-code",
                    "config_path": None,
                    "prd_path": "/tmp/p.md",  # noqa: S108
                    "workspace_path": "/tmp/ws",  # noqa: S108
                    "reason": "test",
                    "kind": "rpd",
                },
            )

    def test_z_suffix_is_accepted(self) -> None:
        rec = ScheduledResume.from_json_dict(
            {
                "session_id": "x",
                "scheduled_at": "2026-05-01T14:00:00Z",
                "resume_at": "2026-05-01T19:00:00Z",
                "cli_agent": "claude-code",
                "config_path": None,
                "prd_path": "/tmp/p.md",  # noqa: S108
                "workspace_path": "/tmp/ws",  # noqa: S108
                "reason": "ok",
                "kind": "rpd",
            },
        )
        assert rec.resume_at.tzinfo is UTC
