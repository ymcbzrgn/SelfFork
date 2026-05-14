"""Tests for :class:`selffork_shared.quota.QuotaSnapshot` and friends."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from selffork_shared.quota import (
    ContextState,
    QuotaSnapshot,
    WindowKind,
    WindowState,
)


def _ts(offset_seconds: int = 0) -> datetime:
    return datetime.now(tz=UTC) + timedelta(seconds=offset_seconds)


# ── WindowState ──────────────────────────────────────────────────────────


def test_window_state_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        WindowState(
            used_pct=50.0,
            resets_at=datetime(2026, 5, 9, 14, 30),
            window_seconds=18000,
        )


def test_window_state_normalizes_non_utc_to_utc() -> None:
    eastern = timezone(timedelta(hours=-5))
    ws = WindowState(
        used_pct=50.0,
        resets_at=datetime(2026, 5, 9, 14, 30, tzinfo=eastern),
        window_seconds=18000,
    )
    assert ws.resets_at.tzinfo is UTC


def test_window_state_pct_bounds() -> None:
    with pytest.raises(ValidationError):
        WindowState(used_pct=-1.0, resets_at=_ts(60), window_seconds=60)
    with pytest.raises(ValidationError):
        WindowState(used_pct=100.5, resets_at=_ts(60), window_seconds=60)


def test_window_state_window_seconds_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        WindowState(used_pct=10.0, resets_at=_ts(60), window_seconds=0)


# ── ContextState ─────────────────────────────────────────────────────────


def test_context_state_clamps_used_pct_above_100() -> None:
    cs = ContextState(used_tokens=999_999, total_tokens=1000, used_pct=99_999.0)
    assert cs.used_pct == 100.0


def test_context_state_total_tokens_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ContextState(used_tokens=10, total_tokens=0, used_pct=10.0)


# ── QuotaSnapshot ────────────────────────────────────────────────────────


def test_quota_snapshot_minimal() -> None:
    snap = QuotaSnapshot(cli_id="claude-code", captured_at=_ts(0), source="test")
    assert snap.cli_id == "claude-code"
    assert snap.windows == {}
    assert snap.context is None
    assert snap.account_id is None
    assert snap.schema_version == "1"


def test_quota_snapshot_rejects_naive_captured_at() -> None:
    with pytest.raises(ValidationError):
        QuotaSnapshot(
            cli_id="x",
            captured_at=datetime(2026, 5, 9),
            source="test",
        )


def test_quota_snapshot_strips_cli_id() -> None:
    snap = QuotaSnapshot(cli_id="  claude-code  ", captured_at=_ts(0), source="t")
    assert snap.cli_id == "claude-code"


def test_quota_snapshot_rejects_empty_cli_id() -> None:
    with pytest.raises(ValidationError):
        QuotaSnapshot(cli_id="   ", captured_at=_ts(0), source="t")


def test_quota_snapshot_is_exhausted() -> None:
    snap = QuotaSnapshot(
        cli_id="claude-code",
        captured_at=_ts(0),
        source="test",
        windows={
            WindowKind.five_hour: WindowState(
                used_pct=96.0,
                resets_at=_ts(60),
                window_seconds=18000,
            ),
            WindowKind.seven_day: WindowState(
                used_pct=20.0,
                resets_at=_ts(60),
                window_seconds=604800,
            ),
        },
    )
    assert snap.is_exhausted() is True
    assert snap.is_exhausted(threshold_pct=99.0) is False


def test_quota_snapshot_soonest_reset() -> None:
    near = _ts(60)
    far = _ts(86400)
    snap = QuotaSnapshot(
        cli_id="codex",
        captured_at=_ts(0),
        source="test",
        windows={
            WindowKind.five_hour: WindowState(
                used_pct=10.0,
                resets_at=far,
                window_seconds=18000,
            ),
            WindowKind.seven_day: WindowState(
                used_pct=10.0,
                resets_at=near,
                window_seconds=604800,
            ),
        },
    )
    assert snap.soonest_reset() == near.astimezone(UTC)


def test_quota_snapshot_soonest_reset_empty() -> None:
    snap = QuotaSnapshot(cli_id="x", captured_at=_ts(0), source="test")
    assert snap.soonest_reset() is None


def test_quota_snapshot_age_seconds() -> None:
    snap = QuotaSnapshot(cli_id="x", captured_at=_ts(-30), source="test")
    assert 29.0 <= snap.age_seconds() <= 31.0


def test_quota_snapshot_age_seconds_with_explicit_now() -> None:
    snap = QuotaSnapshot(cli_id="x", captured_at=_ts(0), source="test")
    age = snap.age_seconds(now=_ts(60))
    assert 59.5 <= age <= 60.5


def test_quota_snapshot_round_trip_json() -> None:
    snap = QuotaSnapshot(
        cli_id="codex",
        captured_at=_ts(0),
        source="rollout",
        context=ContextState(used_tokens=100, total_tokens=200_000, used_pct=0.05),
        windows={
            WindowKind.five_hour: WindowState(
                used_pct=23.5,
                resets_at=_ts(3600),
                window_seconds=18000,
            ),
        },
    )
    payload = snap.model_dump_json()
    rehydrated = QuotaSnapshot.model_validate_json(payload)
    assert rehydrated == snap
