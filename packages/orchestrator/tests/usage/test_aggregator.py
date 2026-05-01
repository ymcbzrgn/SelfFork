"""Unit tests for :class:`UsageAggregator` — synthetic audit fixtures, real I/O."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from selffork_orchestrator.resume.store import (
    ScheduledResume,
    ScheduledResumeStore,
)
from selffork_orchestrator.usage.aggregator import (
    UsageAggregator,
    UsageAggregatorConfig,
)


def _emit(
    audit_path: Path,
    *,
    ts: datetime,
    category: str,
    payload: dict[str, object],
    session_id: str = "01HJTESTSESSION",
) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": ts.isoformat(),
                    "correlation_id": "01HJTESTCORRELATIONABCDEF",
                    "session_id": session_id,
                    "category": category,
                    "level": "INFO",
                    "event": "test",
                    "payload": payload,
                },
            )
            + "\n",
        )


def _config(
    audit_dirs: list[Path],
    *,
    now: datetime,
    resume_root: Path | None = None,
) -> UsageAggregatorConfig:
    store = ScheduledResumeStore(root=resume_root) if resume_root else None
    return UsageAggregatorConfig(
        audit_dirs=tuple(audit_dirs),
        resume_store=store,
        now=now,
    )


class TestEmpty:
    def test_no_dirs_returns_empty(self, tmp_path: Path) -> None:
        cfg = _config([tmp_path / "missing"], now=datetime.now(UTC))
        assert UsageAggregator(cfg).aggregate() == []

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        d = tmp_path / "audit"
        d.mkdir()
        cfg = _config([d], now=datetime.now(UTC))
        assert UsageAggregator(cfg).aggregate() == []


class TestCounting:
    def test_counts_invokes_within_window(self, tmp_path: Path) -> None:
        # Three claude invokes inside the 5h window, one outside.
        now = datetime(2026, 5, 1, 18, 0, 0, tzinfo=UTC)
        d = tmp_path / "audit"
        log = d / "01HJ.jsonl"
        for offset_min in (5, 60, 240, 600):  # last one is 10h ago
            _emit(
                log,
                ts=now - timedelta(minutes=offset_min),
                category="agent.invoke",
                payload={
                    "round": 0,
                    "binary": "/Users/x/.local/bin/claude",
                    "args_count": 3,
                },
            )
        rows = UsageAggregator(_config([d], now=now)).aggregate()
        assert len(rows) == 1
        assert rows[0].cli_agent == "claude-code"
        assert rows[0].window_label == "5h"
        assert rows[0].calls_in_window == 3

    def test_groups_by_cli(self, tmp_path: Path) -> None:
        # Mixed claude + gemini in two separate session files.
        now = datetime(2026, 5, 1, 18, 0, 0, tzinfo=UTC)
        d = tmp_path / "audit"
        for cli_path, fname in (
            ("/opt/homebrew/bin/claude", "claude.jsonl"),
            ("/usr/local/bin/gemini", "gemini.jsonl"),
        ):
            log = d / fname
            _emit(
                log,
                ts=now - timedelta(minutes=10),
                category="agent.invoke",
                payload={"round": 0, "binary": cli_path, "args_count": 1},
            )
            _emit(
                log,
                ts=now - timedelta(minutes=20),
                category="agent.invoke",
                payload={"round": 1, "binary": cli_path, "args_count": 1},
            )
        rows = UsageAggregator(_config([d], now=now)).aggregate()
        # Sorted by cli_agent name.
        assert [r.cli_agent for r in rows] == ["claude-code", "gemini-cli"]
        assert all(r.calls_in_window == 2 for r in rows)

    def test_recovers_cli_from_sandbox_exec_command_list(self, tmp_path: Path) -> None:
        # Older audit shape uses sandbox.exec with command=[binary, ...]
        # — aggregator must still attribute correctly.
        now = datetime(2026, 5, 1, 18, 0, 0, tzinfo=UTC)
        d = tmp_path / "audit"
        log = d / "session.jsonl"
        _emit(
            log,
            ts=now - timedelta(minutes=5),
            category="sandbox.exec",
            payload={
                "command": ["/opt/homebrew/bin/opencode", "run", "msg"],
                "cwd": "/tmp/x",  # noqa: S108 — fixture path
                "pid": 1,
            },
        )
        # An invoke event for the same session ties the count.
        _emit(
            log,
            ts=now - timedelta(minutes=4),
            category="agent.invoke",
            payload={
                "round": 0,
                "binary": "/opt/homebrew/bin/opencode",
                "args_count": 3,
            },
        )
        rows = UsageAggregator(_config([d], now=now)).aggregate()
        assert len(rows) == 1
        assert rows[0].cli_agent == "opencode"
        assert rows[0].calls_in_window == 1


class TestRateLimitRecovery:
    def test_last_rate_limited_at(self, tmp_path: Path) -> None:
        now = datetime(2026, 5, 1, 18, 0, 0, tzinfo=UTC)
        d = tmp_path / "audit"
        log = d / "01HJ.jsonl"
        _emit(
            log,
            ts=now - timedelta(minutes=10),
            category="agent.invoke",
            payload={"binary": "/x/claude", "args_count": 1},
        )
        rl_ts = now - timedelta(minutes=5)
        _emit(
            log,
            ts=rl_ts,
            category="agent.rate_limited",
            payload={
                "reason": "synthetic",
                "kind": "rpd",
                "resume_at_iso": (now + timedelta(hours=2)).isoformat(),
            },
        )
        rows = UsageAggregator(_config([d], now=now)).aggregate()
        assert len(rows) == 1
        assert rows[0].last_rate_limited_at is not None
        # Truncate sub-second drift from JSON round-trip.
        assert rows[0].last_rate_limited_at.replace(microsecond=0) == rl_ts.replace(microsecond=0)
        assert rows[0].next_reset_at is not None

    def test_resume_store_supplies_next_reset(self, tmp_path: Path) -> None:
        now = datetime(2026, 5, 1, 18, 0, 0, tzinfo=UTC)
        d = tmp_path / "audit"
        log = d / "01HJ.jsonl"
        _emit(
            log,
            ts=now - timedelta(minutes=10),
            category="agent.invoke",
            payload={"binary": "/x/claude", "args_count": 1},
        )
        # No agent.rate_limited event in the audit; the resume store
        # carries the reset moment instead.
        resume_root = tmp_path / "scheduled"
        resume_root.mkdir()
        store = ScheduledResumeStore(root=resume_root)
        store.save(
            ScheduledResume(
                session_id="01HJTEST",
                scheduled_at=now,
                resume_at=now + timedelta(hours=3),
                cli_agent="claude-code",
                config_path=None,
                prd_path="/tmp/prd.md",  # noqa: S108
                workspace_path="/tmp/ws",  # noqa: S108
                reason="test",
                kind="rpd",
            ),
        )
        cfg = _config([d], now=now, resume_root=resume_root)
        rows = UsageAggregator(cfg).aggregate()
        assert len(rows) == 1
        assert rows[0].next_reset_at is not None
        assert rows[0].next_reset_at > now

    def test_picks_earliest_future_reset(self, tmp_path: Path) -> None:
        # Both audit and resume store carry resets; we surface the
        # closer one (so the dashboard shows the next event the user
        # actually cares about).
        now = datetime(2026, 5, 1, 18, 0, 0, tzinfo=UTC)
        d = tmp_path / "audit"
        log = d / "01HJ.jsonl"
        _emit(
            log,
            ts=now - timedelta(minutes=10),
            category="agent.invoke",
            payload={"binary": "/x/claude", "args_count": 1},
        )
        _emit(
            log,
            ts=now - timedelta(minutes=5),
            category="agent.rate_limited",
            payload={
                "reason": "x",
                "kind": "rpd",
                # Far-future reset from audit.
                "resume_at_iso": (now + timedelta(hours=10)).isoformat(),
            },
        )
        resume_root = tmp_path / "scheduled"
        resume_root.mkdir()
        store = ScheduledResumeStore(root=resume_root)
        store.save(
            ScheduledResume(
                session_id="01HJTEST",
                scheduled_at=now,
                # Closer reset from the resume store.
                resume_at=now + timedelta(hours=2),
                cli_agent="claude-code",
                config_path=None,
                prd_path="/tmp/prd.md",  # noqa: S108
                workspace_path="/tmp/ws",  # noqa: S108
                reason="test",
                kind="rpd",
            ),
        )
        cfg = _config([d], now=now, resume_root=resume_root)
        rows = UsageAggregator(cfg).aggregate()
        # The earlier (2h) reset wins.
        assert rows[0].next_reset_at is not None
        assert rows[0].next_reset_at < now + timedelta(hours=3)


class TestRobustness:
    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        # Mixed valid + malformed JSON lines.
        now = datetime(2026, 5, 1, 18, 0, 0, tzinfo=UTC)
        d = tmp_path / "audit"
        log = d / "01HJ.jsonl"
        log.parent.mkdir(parents=True)
        with log.open("w", encoding="utf-8") as f:
            f.write("not json\n")
            f.write(
                json.dumps(
                    {
                        "ts": (now - timedelta(minutes=1)).isoformat(),
                        "correlation_id": "x",
                        "session_id": "01HJ",
                        "category": "agent.invoke",
                        "level": "INFO",
                        "event": "x",
                        "payload": {"binary": "/x/claude", "args_count": 1},
                    },
                )
                + "\n",
            )
            f.write("[invalid array]\n")
        rows = UsageAggregator(_config([d], now=now)).aggregate()
        assert len(rows) == 1
        assert rows[0].calls_in_window == 1

    def test_unrelated_events_do_not_count(self, tmp_path: Path) -> None:
        now = datetime(2026, 5, 1, 18, 0, 0, tzinfo=UTC)
        d = tmp_path / "audit"
        log = d / "01HJ.jsonl"
        for cat in ("plan.save", "session.state", "agent.output"):
            _emit(
                log,
                ts=now - timedelta(minutes=1),
                category=cat,
                payload={"x": 1},
            )
        rows = UsageAggregator(_config([d], now=now)).aggregate()
        assert rows == []
