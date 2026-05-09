"""Tests for :class:`CodexSnapper` (rollout JSONL → QuotaSnapshot)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from selffork_orchestrator.snappers.codex import CodexSnapper
from selffork_shared.quota import WindowKind


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _make_codex_home(tmp_path: Path, *, with_auth: bool = True) -> Path:
    home = tmp_path / ".codex"
    home.mkdir()
    if with_auth:
        (home / "auth.json").write_text(
            json.dumps({"OPENAI_API_KEY": None, "tokens": {"access_token": "fake"}}),
        )
    return home


def _write_rollout(
    codex_home: Path,
    *,
    when: datetime,
    events: list[dict[str, object]],
) -> Path:
    sessions = (
        codex_home
        / "sessions"
        / f"{when.year:04d}"
        / f"{when.month:02d}"
        / f"{when.day:02d}"
    )
    sessions.mkdir(parents=True)
    rollout = sessions / "rollout-test.jsonl"
    rollout.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return rollout


@pytest.mark.anyio
async def test_returns_none_when_auth_missing(tmp_path: Path) -> None:
    home = _make_codex_home(tmp_path, with_auth=False)
    assert await CodexSnapper(codex_home=home).snapshot() is None


@pytest.mark.anyio
async def test_returns_none_when_no_rollout(tmp_path: Path) -> None:
    home = _make_codex_home(tmp_path)
    assert await CodexSnapper(codex_home=home).snapshot() is None


@pytest.mark.anyio
async def test_parses_token_count_event(tmp_path: Path) -> None:
    home = _make_codex_home(tmp_path)
    when = datetime.now(tz=UTC)
    _write_rollout(
        home,
        when=when,
        events=[
            {
                "type": "event_msg",
                "timestamp": when.isoformat().replace("+00:00", "Z"),
                "payload": {
                    "type": "token_count",
                    "info": {
                        "model_context_window": 200_000,
                        "total_token_usage": {
                            "input_tokens": 1000,
                            "output_tokens": 500,
                            "reasoning_tokens": 200,
                        },
                    },
                    "rate_limits": {
                        "primary": {
                            "used_percent": 23.5,
                            "window_minutes": 300,
                            "resets_in_seconds": 12345,
                        },
                        "secondary": {
                            "used_percent": 41.2,
                            "window_minutes": 10079,
                            "resets_in_seconds": 234567,
                        },
                    },
                },
            },
        ],
    )

    snap = await CodexSnapper(codex_home=home).snapshot()
    assert snap is not None
    assert snap.cli_id == "codex"

    assert snap.context is not None
    assert snap.context.used_tokens == 1700
    assert snap.context.total_tokens == 200_000

    assert snap.windows[WindowKind.five_hour].used_pct == 23.5
    assert snap.windows[WindowKind.seven_day].used_pct == 41.2
    # Resets_at should be captured_at + resets_in_seconds.
    delta = snap.windows[WindowKind.five_hour].resets_at - snap.captured_at
    assert 12000 <= delta.total_seconds() <= 13000


@pytest.mark.anyio
async def test_picks_latest_token_count_in_file(tmp_path: Path) -> None:
    home = _make_codex_home(tmp_path)
    when = datetime.now(tz=UTC)
    _write_rollout(
        home,
        when=when,
        events=[
            {
                "type": "event_msg",
                "timestamp": when.isoformat().replace("+00:00", "Z"),
                "payload": {
                    "type": "token_count",
                    "info": {
                        "model_context_window": 200_000,
                        "total_token_usage": {"input_tokens": 100},
                    },
                    "rate_limits": {
                        "primary": {
                            "used_percent": 5.0,
                            "window_minutes": 300,
                            "resets_in_seconds": 60,
                        },
                    },
                },
            },
            {"type": "event_msg", "payload": {"type": "agent_message"}},
            {
                "type": "event_msg",
                "timestamp": when.isoformat().replace("+00:00", "Z"),
                "payload": {
                    "type": "token_count",
                    "info": {
                        "model_context_window": 200_000,
                        "total_token_usage": {"input_tokens": 999},
                    },
                    "rate_limits": {
                        "primary": {
                            "used_percent": 88.8,
                            "window_minutes": 300,
                            "resets_in_seconds": 60,
                        },
                    },
                },
            },
        ],
    )
    snap = await CodexSnapper(codex_home=home).snapshot()
    assert snap is not None
    assert snap.context is not None
    assert snap.context.used_tokens == 999  # latest
    assert snap.windows[WindowKind.five_hour].used_pct == 88.8


@pytest.mark.anyio
async def test_returns_none_on_no_token_count(tmp_path: Path) -> None:
    home = _make_codex_home(tmp_path)
    when = datetime.now(tz=UTC)
    _write_rollout(
        home,
        when=when,
        events=[
            {"type": "event_msg", "payload": {"type": "agent_message"}},
            {"type": "session_meta"},
        ],
    )
    snap = await CodexSnapper(codex_home=home).snapshot()
    assert snap is None


@pytest.mark.anyio
async def test_cached_tokens_not_double_counted(tmp_path: Path) -> None:
    """Both ``cached_input_tokens`` and ``cached_tokens`` may surface in the
    same record during Codex schema migrations. The snapper must give the
    former precedence and never sum both, otherwise context utilisation
    over-reports the cache (and silently clamps to 100% via ContextState).
    """
    home = _make_codex_home(tmp_path)
    when = datetime.now(tz=UTC)
    _write_rollout(
        home,
        when=when,
        events=[
            {
                "type": "event_msg",
                "timestamp": when.isoformat().replace("+00:00", "Z"),
                "payload": {
                    "type": "token_count",
                    "info": {
                        "model_context_window": 200_000,
                        "total_token_usage": {
                            "input_tokens": 1000,
                            "output_tokens": 500,
                            "cached_input_tokens": 200,
                            "cached_tokens": 200,
                        },
                    },
                },
            },
        ],
    )
    snap = await CodexSnapper(codex_home=home).snapshot()
    assert snap is not None
    assert snap.context is not None
    # 1000 + 500 + 200 (cached_input_tokens wins) — not 1900.
    assert snap.context.used_tokens == 1700


@pytest.mark.anyio
async def test_cached_tokens_fallback_when_input_variant_absent(tmp_path: Path) -> None:
    home = _make_codex_home(tmp_path)
    when = datetime.now(tz=UTC)
    _write_rollout(
        home,
        when=when,
        events=[
            {
                "type": "event_msg",
                "timestamp": when.isoformat().replace("+00:00", "Z"),
                "payload": {
                    "type": "token_count",
                    "info": {
                        "model_context_window": 200_000,
                        "total_token_usage": {
                            "input_tokens": 1000,
                            "output_tokens": 500,
                            "cached_tokens": 300,
                        },
                    },
                },
            },
        ],
    )
    snap = await CodexSnapper(codex_home=home).snapshot()
    assert snap is not None
    assert snap.context is not None
    # 1000 + 500 + 300 (cached_tokens fallback applied).
    assert snap.context.used_tokens == 1800
