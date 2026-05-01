"""Unit tests for :class:`TmuxSpawnRunner` — child spawning + aggregation.

Tmux is mocked via the abstract :class:`TmuxDriver` interface; we feed
the runner a fake driver that records every call and lets the test
control pane lifecycle without an actual tmux server.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from selffork_orchestrator.spawn.runner import (
    SpawnRunnerConfig,
    TmuxSpawnRunner,
    _parse_exit,
    _tail_lines,
)
from selffork_orchestrator.spawn.sentinel import SpawnRequest
from selffork_orchestrator.tmux.base import TmuxDriver


class _FakeTmux(TmuxDriver):
    """Records driver calls; produces deterministic pane lifecycles.

    By default every pane is "alive" for the first poll and "dead"
    thereafter — so ``__call__`` exits after one polling cycle. Tests
    that need to write log content do so via ``log_writers``.
    """

    def __init__(self) -> None:
        self.create_calls: list[str] = []
        self.add_calls: list[tuple[str, str, Path]] = []
        self.alive_calls: list[str] = []
        self.kill_calls: list[str] = []
        # session_id → pane index → liveness ticks remaining
        self._alive_ticks: dict[str, int] = {}
        self._next_pane_id = 0
        # Pre-populate logs by pane_id at add_pane time.
        self._log_writers: dict[str, str] = {}

    def queue_log(self, pane_index_in_session: int, content: str) -> None:
        # The pane id we'll generate for the Nth add_pane call.
        pane_id = f"%{pane_index_in_session}"
        self._log_writers[pane_id] = content

    async def create_session(self, *, name: str) -> str:
        self.create_calls.append(name)
        self._alive_ticks[name] = 0
        return name

    async def add_pane(
        self,
        *,
        session_id: str,
        command: str,
        log_path: Path,
    ) -> str:
        pane_id = f"%{self._next_pane_id}"
        self._next_pane_id += 1
        self.add_calls.append((session_id, command, log_path))
        # Mark this pane "alive" for one poll cycle.
        self._alive_ticks[pane_id] = 1
        # Write any pre-queued log content so _aggregate has something
        # to read (as if the child process had run).
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if pane_id in self._log_writers:
            log_path.write_text(self._log_writers[pane_id], encoding="utf-8")
        else:
            log_path.touch(exist_ok=True)
        return pane_id

    async def is_pane_alive(self, *, pane_id: str) -> bool:
        self.alive_calls.append(pane_id)
        ticks = self._alive_ticks.get(pane_id, 0)
        if ticks > 0:
            self._alive_ticks[pane_id] = ticks - 1
            return True
        return False

    async def kill_session(self, *, session_id: str) -> None:
        self.kill_calls.append(session_id)


def _config(tmp_path: Path) -> SpawnRunnerConfig:
    return SpawnRunnerConfig(
        selffork_script=Path("/usr/local/bin/selffork"),
        config_path=None,
        shared_host="127.0.0.1",
        shared_port=8080,
        log_root=tmp_path / "spawned",
        poll_interval_seconds=0.01,
    )


class TestRunnerLifecycle:
    @pytest.mark.asyncio
    async def test_spawns_each_request_writes_prd_files(self, tmp_path: Path) -> None:
        tmux = _FakeTmux()
        # Pre-queue one OK log per pane so _aggregate has content.
        tmux.queue_log(0, "child 0 stdout\n[SELFFORK:EXIT:0]\n")
        tmux.queue_log(1, "child 1 stdout\n[SELFFORK:EXIT:0]\n")

        runner = TmuxSpawnRunner(tmux=tmux, config=_config(tmp_path))
        out = await runner(
            parent_session_id="01HJTESTSESSIONABCDEFGHIJK",
            requests=[
                SpawnRequest(index=0, spec="build divide.py"),
                SpawnRequest(index=1, spec="build subtract.py"),
            ],
        )
        # Tmux session created + killed.
        assert len(tmux.create_calls) == 1
        assert tmux.create_calls == tmux.kill_calls
        # Two panes added.
        assert len(tmux.add_calls) == 2
        # Each child's PRD file was written under the parent's spawn dir.
        spawn_dir = tmp_path / "spawned" / "01HJTESTSESSIONABCDEFGHIJK"
        assert (spawn_dir / "spec-00.md").is_file()
        assert (spawn_dir / "spec-01.md").is_file()
        # The aggregator includes both children with status OK.
        assert "Child 0: OK" in out
        assert "Child 1: OK" in out
        assert "build divide.py" in out
        assert "build subtract.py" in out

    @pytest.mark.asyncio
    async def test_failed_child_status_in_aggregator(self, tmp_path: Path) -> None:
        tmux = _FakeTmux()
        tmux.queue_log(0, "things went wrong\n[SELFFORK:EXIT:1]\n")
        runner = TmuxSpawnRunner(tmux=tmux, config=_config(tmp_path))
        out = await runner(
            parent_session_id="P1",
            requests=[SpawnRequest(index=0, spec="break things")],
        )
        assert "FAILED (exit 1)" in out

    @pytest.mark.asyncio
    async def test_command_carries_shared_runtime_env(self, tmp_path: Path) -> None:
        tmux = _FakeTmux()
        tmux.queue_log(0, "[SELFFORK:EXIT:0]\n")
        runner = TmuxSpawnRunner(
            tmux=tmux,
            config=SpawnRunnerConfig(
                selffork_script=Path("/venv/bin/selffork"),
                config_path=Path("/etc/selffork.yaml"),
                shared_host="10.0.0.5",
                shared_port=9090,
                log_root=tmp_path / "spawned",
                poll_interval_seconds=0.01,
            ),
        )
        await runner(
            parent_session_id="P2",
            requests=[SpawnRequest(index=0, spec="x")],
        )
        assert len(tmux.add_calls) == 1
        cmd = tmux.add_calls[0][1]
        assert "SELFFORK_RUNTIME__MODE=shared" in cmd
        assert "SELFFORK_RUNTIME__PORT=9090" in cmd
        assert "10.0.0.5" in cmd
        assert "/venv/bin/selffork" in cmd
        assert "--config" in cmd
        assert "/etc/selffork.yaml" in cmd
        # Exit sentinel is appended for parser recovery.
        assert "[SELFFORK:EXIT:$?]" in cmd

    @pytest.mark.asyncio
    async def test_polling_loop_completes_within_reasonable_time(self, tmp_path: Path) -> None:
        tmux = _FakeTmux()
        runner = TmuxSpawnRunner(tmux=tmux, config=_config(tmp_path))
        # Should finish quickly because _FakeTmux.is_pane_alive returns
        # False after one tick by default (poll interval is 0.01s).
        await asyncio.wait_for(
            runner(
                parent_session_id="P3",
                requests=[SpawnRequest(index=0, spec="x")],
            ),
            timeout=3.0,
        )

    @pytest.mark.asyncio
    async def test_kill_session_runs_even_on_exception(self, tmp_path: Path) -> None:
        # If add_pane raises mid-loop, kill_session must still fire so
        # we don't leak tmux sessions.
        class _BoomTmux(_FakeTmux):
            async def add_pane(self, *, session_id: str, command: str, log_path: Path) -> str:
                del session_id, command, log_path
                raise RuntimeError("synthetic")

        tmux = _BoomTmux()
        runner = TmuxSpawnRunner(tmux=tmux, config=_config(tmp_path))
        with pytest.raises(RuntimeError, match="synthetic"):
            await runner(
                parent_session_id="P4",
                requests=[SpawnRequest(index=0, spec="x")],
            )
        assert tmux.kill_calls == tmux.create_calls


class TestParseExit:
    def test_finds_last_exit_sentinel(self) -> None:
        assert _parse_exit("noise\n[SELFFORK:EXIT:0]\nlater\n[SELFFORK:EXIT:5]\n") == 5

    def test_returns_none_when_absent(self) -> None:
        assert _parse_exit("totally clean") is None

    def test_handles_negative(self) -> None:
        assert _parse_exit("[SELFFORK:EXIT:-15]") == -15


class TestTailLines:
    def test_returns_last_n_lines(self) -> None:
        text = "\n".join(f"line{i}" for i in range(50))
        tail = _tail_lines(text, 5)
        assert tail.count("\n") == 4
        assert tail.endswith("line49")

    def test_short_text_returned_intact(self) -> None:
        assert _tail_lines("only one line", 10) == "only one line"
