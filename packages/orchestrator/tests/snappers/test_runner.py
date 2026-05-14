"""Tests for :class:`SnapperRunner` lifecycle."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import anyio
import pytest

from selffork_orchestrator.snappers.base import Snapper
from selffork_orchestrator.snappers.runner import (
    SnapperRunner,
    SnapperRunnerConfig,
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
