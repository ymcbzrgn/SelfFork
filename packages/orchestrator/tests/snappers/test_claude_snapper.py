"""Tests for :class:`ClaudeSnapper` (raw statusline JSON → QuotaSnapshot)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from selffork_orchestrator.snappers.claude import ClaudeSnapper
from selffork_shared.quota import WindowKind


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_returns_none_when_raw_missing(tmp_path: Path) -> None:
    snapper = ClaudeSnapper(raw_path=tmp_path / "missing.json")
    assert await snapper.snapshot() is None


@pytest.mark.anyio
async def test_returns_none_on_partial_json(tmp_path: Path) -> None:
    raw = tmp_path / "claude.json"
    raw.write_text("{not valid json")
    snapper = ClaudeSnapper(raw_path=raw)
    assert await snapper.snapshot() is None


@pytest.mark.anyio
async def test_parses_full_statusline_payload(tmp_path: Path) -> None:
    raw = tmp_path / "claude.json"
    five_hour_reset = int(datetime(2026, 5, 9, 19, 30, tzinfo=UTC).timestamp())
    seven_day_reset = int(datetime(2026, 5, 16, 14, 30, tzinfo=UTC).timestamp())
    raw.write_text(
        json.dumps(
            {
                "model": {"display_name": "Opus 4.7 (1M context)", "id": "claude-opus-4-7"},
                "session_id": "abc-123",
                "context_window": {
                    "context_window_size": 1_000_000,
                    "used_percentage": 9.0,
                    "current_usage": {
                        "input_tokens": 50_000,
                        "output_tokens": 5_000,
                        "cache_creation_input_tokens": 10_000,
                        "cache_read_input_tokens": 30_000,
                    },
                },
                "rate_limits": {
                    "five_hour": {"used_percentage": 40.5, "resets_at": five_hour_reset},
                    "seven_day": {"used_percentage": 32.1, "resets_at": seven_day_reset},
                },
            },
        ),
    )

    snap = await ClaudeSnapper(raw_path=raw).snapshot()
    assert snap is not None
    assert snap.cli_id == "claude-code"
    assert snap.source == "statusline.sh"

    assert snap.context is not None
    # 50_000 + 5_000 + 10_000 + 30_000 = 95_000 (output_tokens included).
    assert snap.context.used_tokens == 95_000
    assert snap.context.total_tokens == 1_000_000

    assert snap.windows[WindowKind.five_hour].used_pct == 40.5
    assert snap.windows[WindowKind.seven_day].used_pct == 32.1
    assert snap.windows[WindowKind.five_hour].resets_at == datetime.fromtimestamp(
        five_hour_reset,
        tz=UTC,
    )


@pytest.mark.anyio
async def test_emits_context_when_rate_limits_absent(tmp_path: Path) -> None:
    """API-key-auth or pre-first-API: rate_limits empty, context still emitted."""
    raw = tmp_path / "claude.json"
    raw.write_text(
        json.dumps(
            {
                "context_window": {
                    "context_window_size": 200_000,
                    "current_usage": {"input_tokens": 1000},
                },
            },
        ),
    )
    snap = await ClaudeSnapper(raw_path=raw).snapshot()
    assert snap is not None
    assert snap.windows == {}
    assert snap.context is not None
    assert snap.context.used_tokens == 1000


@pytest.mark.anyio
async def test_uses_used_percentage_fallback_when_current_usage_empty(
    tmp_path: Path,
) -> None:
    """Pre-first-API may give used_percentage but no current_usage breakdown."""
    raw = tmp_path / "claude.json"
    raw.write_text(
        json.dumps(
            {
                "context_window": {
                    "context_window_size": 1_000_000,
                    "used_percentage": 5.0,
                },
            },
        ),
    )
    snap = await ClaudeSnapper(raw_path=raw).snapshot()
    assert snap is not None
    assert snap.context is not None
    assert snap.context.used_tokens == 50_000  # 5% of 1M


@pytest.mark.anyio
async def test_skips_window_with_invalid_reset(tmp_path: Path) -> None:
    raw = tmp_path / "claude.json"
    raw.write_text(
        json.dumps(
            {
                "context_window": {"context_window_size": 200_000},
                "rate_limits": {
                    "five_hour": {"used_percentage": 50.0, "resets_at": "not-a-number"},
                    "seven_day": {"used_percentage": 25.0, "resets_at": 1746000000},
                },
            },
        ),
    )
    snap = await ClaudeSnapper(raw_path=raw).snapshot()
    assert snap is not None
    assert WindowKind.five_hour not in snap.windows
    assert WindowKind.seven_day in snap.windows
