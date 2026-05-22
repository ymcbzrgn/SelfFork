"""S-Auto Faz E — AuditEntry + AuditWriter + build_audit_entry tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from selffork_orchestrator.heartbeat.actions import LegalAction
from selffork_orchestrator.heartbeat.audit import (
    AuditEntry,
    AuditWriter,
    build_audit_entry,
    default_audit_path,
)
from selffork_orchestrator.heartbeat.deliberation import ActionDecision
from selffork_orchestrator.heartbeat.executor import ActionResult
from selffork_orchestrator.heartbeat.filter import (
    DEFAULT_CLI_IDS,
    DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT,
    WorldState,
)
from selffork_shared.quota import QuotaSnapshot, WindowKind, WindowState


def _quota(cli_id: str, used_pct: float = 25.0) -> QuotaSnapshot:
    now = datetime.now(UTC)
    return QuotaSnapshot(
        cli_id=cli_id,
        windows={
            WindowKind.five_hour: WindowState(
                used_pct=used_pct,
                resets_at=now + timedelta(hours=5),
                window_seconds=18000,
            ),
        },
        captured_at=now,
        source="test",
    )


def _state(**overrides: object) -> WorldState:
    base: dict[str, object] = dict(
        pause_active=False,
        within_active_hours=True,
        active_concurrent_sessions=0,
        max_concurrent_sessions=1,
        creative_mode_enabled=False,
        cli_quota={cli: _quota(cli) for cli in DEFAULT_CLI_IDS},
        quota_exhaustion_threshold_pct=DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT,
        supervised_mode=False,
        last_active_workspace="alpha",
    )
    base.update(overrides)
    return WorldState(**base)  # type: ignore[arg-type]


# ── AuditEntry ────────────────────────────────────────────────────


def test_audit_entry_minimal_fields() -> None:
    entry = AuditEntry(
        tick=1,
        timestamp=datetime.now(UTC),
        trigger="kanban.changed",
    )
    assert entry.tick == 1
    assert entry.legal_actions == []
    assert entry.air_alert is None


def test_audit_entry_rejects_negative_tick() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AuditEntry(tick=-1, timestamp=datetime.now(UTC), trigger="t")


def test_audit_entry_as_jsonl_ends_with_newline() -> None:
    entry = AuditEntry(tick=0, timestamp=datetime.now(UTC), trigger="t")
    line = entry.as_jsonl()
    assert line.endswith("\n")
    # Strip newline and confirm round-trip.
    payload = json.loads(line.strip())
    assert payload["tick"] == 0
    assert payload["trigger"] == "t"


def test_audit_entry_is_frozen() -> None:
    entry = AuditEntry(tick=0, timestamp=datetime.now(UTC), trigger="t")
    with pytest.raises(ValidationError):
        entry.tick = 5  # type: ignore[misc]


# ── AuditWriter ───────────────────────────────────────────────────


def test_audit_writer_creates_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "audit.jsonl"
    writer = AuditWriter(path=target)
    entry = AuditEntry(tick=0, timestamp=datetime.now(UTC), trigger="t")
    writer.write(entry)
    assert target.is_file()


def test_audit_writer_appends_lines(tmp_path: Path) -> None:
    target = tmp_path / "audit.jsonl"
    writer = AuditWriter(path=target)
    for i in range(3):
        writer.write(
            AuditEntry(tick=i, timestamp=datetime.now(UTC), trigger="t")
        )
    lines = target.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    for i, line in enumerate(lines):
        payload = json.loads(line)
        assert payload["tick"] == i


def test_audit_writer_read_all_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "audit.jsonl"
    writer = AuditWriter(path=target)
    for i in range(2):
        writer.write(
            AuditEntry(
                tick=i,
                timestamp=datetime.now(UTC),
                trigger="reconciliation",
            )
        )
    entries = list(writer.read_all())
    assert len(entries) == 2
    assert entries[0].tick == 0
    assert entries[1].tick == 1


def test_audit_writer_read_all_skips_malformed_lines(tmp_path: Path) -> None:
    target = tmp_path / "audit.jsonl"
    writer = AuditWriter(path=target)
    writer.write(AuditEntry(tick=0, timestamp=datetime.now(UTC), trigger="t"))
    # Append a garbage line.
    with target.open("a", encoding="utf-8") as fp:
        fp.write("{not json\n")
    writer.write(AuditEntry(tick=1, timestamp=datetime.now(UTC), trigger="t"))
    entries = list(writer.read_all())
    assert [e.tick for e in entries] == [0, 1]


def test_audit_writer_read_all_absent_file(tmp_path: Path) -> None:
    writer = AuditWriter(path=tmp_path / "does-not-exist.jsonl")
    assert list(writer.read_all()) == []


def test_audit_writer_default_path() -> None:
    assert default_audit_path().name == "audit.jsonl"
    assert default_audit_path().parent.name == "heartbeat"


# ── build_audit_entry ─────────────────────────────────────────────


def test_build_audit_entry_minimal() -> None:
    entry = build_audit_entry(
        tick=5,
        trigger="kanban.changed",
        world_state=_state(),
    )
    assert entry.tick == 5
    assert entry.trigger == "kanban.changed"
    assert entry.world_state["last_active_workspace"] == "alpha"
    assert entry.decision_action is None
    assert entry.result_outcome is None


def test_build_audit_entry_with_decision_and_result() -> None:
    decision = ActionDecision(
        action=LegalAction.TASK_START, reasoning="Login refactor"
    )
    result = ActionResult(
        action=LegalAction.TASK_START,
        outcome="executed",
        summary="spawned pid=42",
        metadata={"pid": 42},
    )
    entry = build_audit_entry(
        tick=7,
        trigger="operator.message",
        world_state=_state(),
        legal_actions=frozenset({"task_başlat", "bekle"}),
        decision=decision,
        result=result,
        air_alert=None,
    )
    assert entry.legal_actions == ["bekle", "task_başlat"]
    assert entry.decision_action == "task_başlat"
    assert entry.decision_reasoning == "Login refactor"
    assert entry.decision_fallback is False
    assert entry.result_outcome == "executed"
    assert entry.result_metadata == {"pid": 42}
    assert entry.idempotency_key == "7:task_başlat:alpha"


def test_build_audit_entry_with_air_alert() -> None:
    entry = build_audit_entry(
        tick=10,
        trigger="reconciliation",
        world_state=_state(),
        air_alert="critical",
    )
    assert entry.air_alert == "critical"


def test_build_audit_entry_includes_quota_summary() -> None:
    entry = build_audit_entry(
        tick=0,
        trigger="t",
        world_state=_state(
            cli_quota={"claude-code": _quota("claude-code", 99.0)},
        ),
    )
    quota = entry.world_state["cli_quota"]
    assert "claude-code" in quota
    assert quota["claude-code"]["exhausted"] is True
    assert quota["claude-code"]["max_pct"] == 99.0


def test_build_audit_entry_idempotency_key_global_fallback() -> None:
    entry = build_audit_entry(
        tick=3,
        trigger="t",
        world_state=_state(last_active_workspace=None),
    )
    assert entry.idempotency_key == "3:noop:global"
