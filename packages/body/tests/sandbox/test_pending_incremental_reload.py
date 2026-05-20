"""Tests for ``PendingConfirmationStore.reload_from_disk`` incremental
replay (audit fix #14)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from selffork_body.sandbox.destructive_whitelist import (
    CandidateAction,
    DestructiveCategory,
    MatchRule,
)
from selffork_body.sandbox.pending_confirmations import PendingConfirmationStore


@pytest.fixture
def category() -> DestructiveCategory:
    return DestructiveCategory(
        id="prod_deploy",
        description="PROD push",
        confirm_window_hours=4,
        match_any=(
            MatchRule(tool="git", args_contains=("push", "origin", "main")),
        ),
    )


def test_reload_skips_known_lines(
    tmp_path: Path, category: DestructiveCategory
) -> None:
    """A second reload after one append only parses the new line."""
    audit_path = tmp_path / "pending.jsonl"
    producer = PendingConfirmationStore(audit_path=audit_path)
    consumer = PendingConfirmationStore(audit_path=audit_path)

    first = producer.request(
        category=category,
        action=CandidateAction(tool="git", args=("push", "origin", "main")),
        workspace_slug="demo",
    )
    consumer.reload_from_disk()
    assert consumer.get(first.id) is not None
    offset_after_first = consumer._audit_file_offset  # type: ignore[attr-defined]
    assert offset_after_first > 0

    # No new appends → reload is a no-op.
    consumer.reload_from_disk()
    assert consumer._audit_file_offset == offset_after_first  # type: ignore[attr-defined]

    # New append → offset advances, new entry visible.
    second = producer.request(
        category=category,
        action=CandidateAction(tool="git", args=("push", "origin", "main")),
        workspace_slug="other",
    )
    consumer.reload_from_disk()
    assert consumer.get(second.id) is not None
    assert consumer._audit_file_offset > offset_after_first  # type: ignore[attr-defined]


def test_reload_detects_truncation(
    tmp_path: Path, category: DestructiveCategory
) -> None:
    """If the JSONL file shrinks (rotation), the consumer full-resets."""
    audit_path = tmp_path / "pending.jsonl"
    producer = PendingConfirmationStore(audit_path=audit_path)
    consumer = PendingConfirmationStore(audit_path=audit_path)

    entry = producer.request(
        category=category,
        action=CandidateAction(tool="git", args=("push", "origin", "main")),
        workspace_slug="demo",
    )
    consumer.reload_from_disk()
    assert consumer.get(entry.id) is not None
    primed_offset = consumer._audit_file_offset  # type: ignore[attr-defined]
    assert primed_offset > 0

    # Simulate log rotation: replace the file with a fresh, smaller one
    # holding a different entry.
    rotated_payload = json.dumps(
        {
            "op": "request",
            "entry": {
                "id": "rot-xyz",
                "workspace_slug": "rotated",
                "category_id": "prod_deploy",
                "category_description": "PROD push",
                "command_summary": "git push origin main",
                "action_payload": {"tool": "git"},
                "asked_at": "2099-01-01T00:00:00+00:00",
                "expires_at": "2099-01-01T04:00:00+00:00",
                "status": "pending",
                "decided_at": None,
                "decided_by": None,
            },
        }
    )
    audit_path.write_text(rotated_payload + "\n", encoding="utf-8")
    # The rotated file is shorter than ``primed_offset``.
    assert audit_path.stat().st_size < primed_offset

    consumer.reload_from_disk()
    # Full reset: stale entry gone, rotated entry visible.
    assert consumer.get(entry.id) is None
    assert consumer.get("rot-xyz") is not None


def test_reload_ignores_corrupt_lines(
    tmp_path: Path, category: DestructiveCategory
) -> None:
    """A JSONL line with invalid JSON / missing fields is skipped, but
    the offset still advances so the consumer doesn't loop forever."""
    audit_path = tmp_path / "pending.jsonl"
    producer = PendingConfirmationStore(audit_path=audit_path)
    consumer = PendingConfirmationStore(audit_path=audit_path)
    producer.request(
        category=category,
        action=CandidateAction(tool="git", args=("push", "origin", "main")),
        workspace_slug=None,
    )
    consumer.reload_from_disk()
    offset = consumer._audit_file_offset  # type: ignore[attr-defined]

    # Append a corrupt line followed by a valid one.
    audit_path.open("a", encoding="utf-8").write(
        "{not valid json}\n"
        + json.dumps(
            {
                "op": "request",
                "entry": {
                    "id": "good-after-bad",
                    "workspace_slug": "demo",
                    "category_id": "prod_deploy",
                    "category_description": "PROD push",
                    "command_summary": "git push origin main",
                    "action_payload": {"tool": "git"},
                    "asked_at": "2099-01-01T00:00:00+00:00",
                    "expires_at": "2099-01-01T04:00:00+00:00",
                    "status": "pending",
                    "decided_at": None,
                    "decided_by": None,
                },
            }
        )
        + "\n"
    )

    consumer.reload_from_disk()
    assert consumer.get("good-after-bad") is not None
    assert consumer._audit_file_offset > offset  # type: ignore[attr-defined]
