"""Unit tests for :class:`LibtmuxDriver` — libtmux mocked, no real tmux.

Real-tmux integration coverage lives under ``tests/e2e/`` and is gated
by ``pytest.mark.skipif(shutil.which("tmux") is None, ...)``. The unit
tests below verify that LibtmuxDriver wires libtmux's API correctly:
which methods it calls, in which order, with which arguments — and how
it maps libtmux exceptions onto SelfFork's typed error hierarchy.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from selffork_orchestrator.tmux.libtmux_driver import (
    LibtmuxDriver,
    _shell_quote,
)
from selffork_shared.errors import TmuxPaneError, TmuxSessionError

# ── Fakes for libtmux ─────────────────────────────────────────────────────────


class _FakeCmdResult:
    def __init__(self, stdout: list[str]) -> None:
        self.stdout = stdout


class _FakePane:
    def __init__(
        self,
        pane_id: str = "%0",
        current_command: str = "zsh",
    ) -> None:
        self.pane_id = pane_id
        self.pane_current_command = current_command
        self.cmd_calls: list[tuple[str, ...]] = []
        self.send_keys_calls: list[tuple[str, bool, bool]] = []
        self.fail_pipe_pane = False
        self.fail_send_keys = False

    def cmd(self, *args: str) -> _FakeCmdResult:
        self.cmd_calls.append(args)
        if args and args[0] == "pipe-pane" and self.fail_pipe_pane:
            raise RuntimeError("pipe-pane boom")
        return _FakeCmdResult([])

    def send_keys(
        self,
        cmd: str,
        *,
        enter: bool = True,
        suppress_history: bool = False,
    ) -> None:
        if self.fail_send_keys:
            raise RuntimeError("send-keys boom")
        self.send_keys_calls.append((cmd, enter, suppress_history))


class _FakeWindow:
    def __init__(self, panes: list[_FakePane]) -> None:
        self.panes = panes
        self.split_calls: list[bool] = []
        self.fail_split = False

    def split(self, *, attach: bool = True) -> _FakePane:
        self.split_calls.append(attach)
        if self.fail_split:
            raise RuntimeError("split boom")
        new_pane = _FakePane(pane_id=f"%{len(self.panes)}")
        self.panes.append(new_pane)
        return new_pane


class _FakeSession:
    def __init__(self, name: str, panes: list[_FakePane] | None = None) -> None:
        self.session_name = name
        self.session_id = f"${name}"
        self.active_window = _FakeWindow(panes or [_FakePane()])


class _FakeServer:
    def __init__(self) -> None:
        self.sessions: list[_FakeSession] = []
        self.kill_calls: list[str] = []
        self.cmd_calls: list[tuple[str, ...]] = []
        self.fail_new_session = False
        self.pane_dead_value = "0"

    def new_session(
        self,
        *,
        session_name: str,
        detach: bool = True,
        kill_session: bool = False,
    ) -> _FakeSession:
        del detach, kill_session
        if self.fail_new_session:
            raise RuntimeError("new-session boom")
        session = _FakeSession(session_name)
        self.sessions.append(session)
        return session

    def kill_session(self, name: str) -> None:
        if not any(s.session_name == name for s in self.sessions):
            raise RuntimeError(f"session not found: {name}")
        self.sessions = [s for s in self.sessions if s.session_name != name]
        self.kill_calls.append(name)

    def cmd(self, *args: str) -> _FakeCmdResult:
        self.cmd_calls.append(args)
        # display-message returns the requested format value on stdout.
        return _FakeCmdResult([self.pane_dead_value])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_driver(monkeypatch: pytest.MonkeyPatch) -> tuple[LibtmuxDriver, _FakeServer]:
    server = _FakeServer()

    def _server_factory() -> _FakeServer:
        return server

    monkeypatch.setattr(
        "selffork_orchestrator.tmux.libtmux_driver.libtmux.Server",
        _server_factory,
    )
    driver = LibtmuxDriver()
    return driver, server


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestInit:
    def test_strips_tmux_env_to_avoid_nesting(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,12345,0")  # noqa: S108 — fake $TMUX value, not a real file
        _make_driver(monkeypatch)
        # After init, TMUX must be unset so libtmux's Server connects to
        # the default socket rather than nesting inside the user's
        # outer tmux.
        assert "TMUX" not in os.environ


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_creates_session_and_returns_name(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        driver, server = _make_driver(monkeypatch)
        session_id = await driver.create_session(name="selffork-abc")
        assert session_id == "selffork-abc"
        assert len(server.sessions) == 1
        assert server.sessions[0].session_name == "selffork-abc"

    @pytest.mark.asyncio
    async def test_libtmux_failure_raises_session_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        driver, server = _make_driver(monkeypatch)
        server.fail_new_session = True
        with pytest.raises(TmuxSessionError, match="failed to create"):
            await driver.create_session(name="x")


class TestAddPane:
    @pytest.mark.asyncio
    async def test_first_pane_reuses_default_pane_pipes_and_runs(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        driver, server = _make_driver(monkeypatch)
        await driver.create_session(name="s1")
        log = tmp_path / "logs" / "pane.log"

        pane_id = await driver.add_pane(
            session_id="s1",
            command="echo hello",
            log_path=log,
        )
        assert pane_id == "%0"
        assert log.parent.is_dir()
        assert log.exists()

        # First pane: no split was needed.
        window = server.sessions[0].active_window
        assert window.split_calls == []

        # pipe-pane was wired with the quoted log path.
        first_pane = window.panes[0]
        assert any(
            args[0] == "pipe-pane" and "-O" in args and str(log) in " ".join(args)
            for args in first_pane.cmd_calls
        )

        # Command was sent with suppress_history=True.
        assert first_pane.send_keys_calls == [("echo hello", True, True)]

    @pytest.mark.asyncio
    async def test_subsequent_pane_splits_window(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        driver, server = _make_driver(monkeypatch)
        await driver.create_session(name="s2")
        log1 = tmp_path / "p1.log"
        log2 = tmp_path / "p2.log"

        # First add reuses default. Driver tracks this internally so the
        # second add splits regardless of what the default pane's
        # current_command looks like (avoids a timing race where
        # send_keys hasn't yet swapped zsh → user-cmd).
        await driver.add_pane(session_id="s2", command="cmd1", log_path=log1)

        pane2 = await driver.add_pane(session_id="s2", command="cmd2", log_path=log2)
        assert pane2 == "%1"
        window = server.sessions[0].active_window
        assert window.split_calls == [False]  # detached split

    @pytest.mark.asyncio
    async def test_three_adds_yield_one_default_plus_two_splits(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # Driver state — not pane state — drives the reuse-vs-split
        # decision. Three adds must produce exactly two splits even when
        # libtmux reports the default pane's current_command as "zsh"
        # the whole time (the regression that broke run-many e2e).
        driver, server = _make_driver(monkeypatch)
        await driver.create_session(name="s_triple")
        for i in range(3):
            await driver.add_pane(
                session_id="s_triple",
                command=f"cmd{i}",
                log_path=tmp_path / f"p{i}.log",
            )
        window = server.sessions[0].active_window
        assert window.split_calls == [False, False]
        assert len(window.panes) == 3

    @pytest.mark.asyncio
    async def test_unknown_session_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        driver, _ = _make_driver(monkeypatch)
        with pytest.raises(TmuxSessionError, match="not found"):
            await driver.add_pane(
                session_id="nope",
                command="x",
                log_path=tmp_path / "x.log",
            )

    @pytest.mark.asyncio
    async def test_pipe_pane_failure_raises_pane_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        driver, server = _make_driver(monkeypatch)
        await driver.create_session(name="s3")
        server.sessions[0].active_window.panes[0].fail_pipe_pane = True
        with pytest.raises(TmuxPaneError, match="pipe-pane"):
            await driver.add_pane(
                session_id="s3",
                command="x",
                log_path=tmp_path / "x.log",
            )

    @pytest.mark.asyncio
    async def test_send_keys_failure_raises_pane_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        driver, server = _make_driver(monkeypatch)
        await driver.create_session(name="s4")
        server.sessions[0].active_window.panes[0].fail_send_keys = True
        with pytest.raises(TmuxPaneError, match="send command"):
            await driver.add_pane(
                session_id="s4",
                command="x",
                log_path=tmp_path / "x.log",
            )


class TestIsPaneAlive:
    @pytest.mark.asyncio
    async def test_returns_true_when_pane_dead_is_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        driver, server = _make_driver(monkeypatch)
        server.pane_dead_value = "0"
        assert await driver.is_pane_alive(pane_id="%0") is True

    @pytest.mark.asyncio
    async def test_returns_false_when_pane_dead_is_one(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        driver, server = _make_driver(monkeypatch)
        server.pane_dead_value = "1"
        assert await driver.is_pane_alive(pane_id="%0") is False

    @pytest.mark.asyncio
    async def test_lookup_failure_treated_as_dead(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        driver, server = _make_driver(monkeypatch)

        def _boom(*_args: Any) -> Any:
            raise RuntimeError("display-message failed")

        server.cmd = _boom  # type: ignore[method-assign]
        assert await driver.is_pane_alive(pane_id="%X") is False


class TestKillSession:
    @pytest.mark.asyncio
    async def test_kills_known_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        driver, server = _make_driver(monkeypatch)
        await driver.create_session(name="s5")
        await driver.kill_session(session_id="s5")
        assert server.kill_calls == ["s5"]
        assert server.sessions == []

    @pytest.mark.asyncio
    async def test_unknown_session_is_idempotent(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        driver, _ = _make_driver(monkeypatch)
        # Must not raise — kill is idempotent by contract.
        await driver.kill_session(session_id="never-existed")


# ── Helper-function tests ─────────────────────────────────────────────────────


class TestShellQuote:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            (Path("simple.log"), "'simple.log'"),
            (Path("with space.log"), "'with space.log'"),
            (Path("he's.log"), "'he'\\''s.log'"),
        ],
    )
    def test_quotes_paths_safely(self, path: Path, expected: str) -> None:
        assert _shell_quote(path) == expected
