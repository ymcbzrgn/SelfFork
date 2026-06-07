"""Tests for :class:`SnapperRunner` lifecycle."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import anyio
import pytest

from selffork_orchestrator.snappers.base import Snapper
from selffork_orchestrator.snappers.runner import (
    DEFAULT_SIDECAR_INTERVAL_SECONDS,
    SnapperRunner,
    SnapperRunnerConfig,
    build_default_snapper_runner,
)
from selffork_shared.quota import (
    ContextState,
    QuotaSnapshot,
    WindowKind,
    WindowState,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeSnapper(Snapper):
    """Test double — returns a static snapshot or raises on demand."""

    def __init__(
        self,
        cli_id: str,
        *,
        snapshot: QuotaSnapshot | None = None,
        raise_on_call: Exception | None = None,
    ) -> None:
        super().__init__(cli_id=cli_id)
        self._snapshot = snapshot
        self._raise = raise_on_call
        self.calls = 0

    async def snapshot(self) -> QuotaSnapshot | None:
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return self._snapshot


def _quota_snapshot(cli_id: str) -> QuotaSnapshot:
    return QuotaSnapshot(
        cli_id=cli_id,
        captured_at=datetime.now(tz=UTC),
        source="test",
        context=ContextState(used_tokens=100, total_tokens=1000, used_pct=10.0),
        windows={
            WindowKind.five_hour: WindowState(
                used_pct=15.0,
                resets_at=datetime.now(tz=UTC),
                window_seconds=18000,
            ),
        },
    )


@pytest.mark.anyio
async def test_runner_writes_snapshot_atomically(tmp_path: Path) -> None:
    fake = _FakeSnapper("claude-code", snapshot=_quota_snapshot("claude-code"))
    runner = SnapperRunner(
        [fake],
        SnapperRunnerConfig(
            state_dir=tmp_path,
            default_interval_seconds=0.05,
            intervals_seconds={"claude-code": 0.05},
        ),
    )

    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.serve)
        # Wait a few ticks then stop.
        await anyio.sleep(0.2)
        runner.stop()

    out = tmp_path / "claude-code.json"
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["cli_id"] == "claude-code"
    assert fake.calls >= 1


@pytest.mark.anyio
async def test_runner_skips_none_snapshots(tmp_path: Path) -> None:
    fake = _FakeSnapper("codex", snapshot=None)
    runner = SnapperRunner(
        [fake],
        SnapperRunnerConfig(
            state_dir=tmp_path,
            default_interval_seconds=0.05,
        ),
    )
    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.serve)
        await anyio.sleep(0.15)
        runner.stop()
    assert not (tmp_path / "codex.json").exists()
    assert fake.calls >= 1


@pytest.mark.anyio
async def test_runner_survives_snapper_exception(tmp_path: Path) -> None:
    bad = _FakeSnapper("opencode", raise_on_call=RuntimeError("boom"))
    good = _FakeSnapper("claude-code", snapshot=_quota_snapshot("claude-code"))
    runner = SnapperRunner(
        [bad, good],
        SnapperRunnerConfig(
            state_dir=tmp_path,
            default_interval_seconds=0.05,
            backoff_seconds=0.1,
        ),
    )
    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.serve)
        await anyio.sleep(0.25)
        runner.stop()
    # The good snapper kept producing despite the bad one throwing.
    assert (tmp_path / "claude-code.json").exists()
    assert good.calls >= 1
    assert bad.calls >= 1


@pytest.mark.anyio
async def test_runner_stop_returns_promptly(tmp_path: Path) -> None:
    fake = _FakeSnapper("gemini-cli", snapshot=_quota_snapshot("gemini-cli"))
    runner = SnapperRunner(
        [fake],
        SnapperRunnerConfig(
            state_dir=tmp_path,
            default_interval_seconds=10.0,  # would loop forever without stop
        ),
    )
    async with anyio.create_task_group() as tg:
        tg.start_soon(runner.serve)
        await anyio.sleep(0.05)
        runner.stop()
    # Reaching here means the task group exited within move_on_after window.


# ── build_default_snapper_runner (dashboard sidecar factory) ──────────────────


def test_build_default_snapper_runner_constructs_full_fleet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default invocation builds a runner wired with every registered snapper."""
    monkeypatch.delenv("SELFFORK_SNAPPER_RUNNER_ENABLED", raising=False)
    monkeypatch.delenv("SELFFORK_SNAPPER_RUNNER_DEFAULT_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("SELFFORK_SNAPPER_RUNNER_STATE_DIR", raising=False)
    runner = build_default_snapper_runner()
    assert runner is not None
    cli_ids = {s.cli_id for s in runner.snappers}
    # Active default fleet = 4 wired CLI agents. minimax-cli + zai are
    # routed via opencode (operator 2026-05-26) so they don't get a
    # standalone snapper here.
    assert cli_ids == {
        "claude-code",
        "codex",
        "gemini-cli",
        "opencode",
    }
    # Default cadence is the dashboard sidecar constant (slower than the
    # per-session 1 Hz default — see DEFAULT_SIDECAR_INTERVAL_SECONDS).
    assert runner.config.default_interval_seconds == DEFAULT_SIDECAR_INTERVAL_SECONDS
    # No state_dir override → consumers (proactive reader) fall back to
    # base.default_state_dir().
    assert runner.config.state_dir is None


def test_build_default_snapper_runner_disabled_via_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SELFFORK_SNAPPER_RUNNER_ENABLED=false`` disables the sidecar."""
    for disabled in ("false", "0", "no", "FALSE", "No"):
        monkeypatch.setenv("SELFFORK_SNAPPER_RUNNER_ENABLED", disabled)
        assert build_default_snapper_runner() is None
    # Any other value (including ``true``, empty) enables (auto-detect).
    monkeypatch.setenv("SELFFORK_SNAPPER_RUNNER_ENABLED", "true")
    assert build_default_snapper_runner() is not None
    monkeypatch.setenv("SELFFORK_SNAPPER_RUNNER_ENABLED", "")
    assert build_default_snapper_runner() is not None


def test_build_default_snapper_runner_honors_interval_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SELFFORK_SNAPPER_RUNNER_ENABLED", raising=False)
    monkeypatch.setenv("SELFFORK_SNAPPER_RUNNER_DEFAULT_INTERVAL_SECONDS", "2.5")
    runner = build_default_snapper_runner()
    assert runner is not None
    assert runner.config.default_interval_seconds == 2.5


def test_build_default_snapper_runner_falls_back_on_invalid_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SELFFORK_SNAPPER_RUNNER_ENABLED", raising=False)
    monkeypatch.setenv("SELFFORK_SNAPPER_RUNNER_DEFAULT_INTERVAL_SECONDS", "not-a-number")
    runner = build_default_snapper_runner()
    assert runner is not None
    assert runner.config.default_interval_seconds == DEFAULT_SIDECAR_INTERVAL_SECONDS


def test_build_default_snapper_runner_clamps_low_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Interval is clamped to >= 0.25s to keep the fleet kind to disk + CPU."""
    monkeypatch.delenv("SELFFORK_SNAPPER_RUNNER_ENABLED", raising=False)
    monkeypatch.setenv("SELFFORK_SNAPPER_RUNNER_DEFAULT_INTERVAL_SECONDS", "0.05")
    runner = build_default_snapper_runner()
    assert runner is not None
    assert runner.config.default_interval_seconds == 0.25


def test_build_default_snapper_runner_honors_state_dir_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SELFFORK_SNAPPER_RUNNER_ENABLED", raising=False)
    monkeypatch.setenv(
        "SELFFORK_SNAPPER_RUNNER_STATE_DIR",
        str(tmp_path / "custom-state"),
    )
    runner = build_default_snapper_runner()
    assert runner is not None
    assert runner.config.state_dir == tmp_path / "custom-state"
