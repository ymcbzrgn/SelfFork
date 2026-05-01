"""Unit tests for :class:`SubprocessSandbox`."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from selffork_orchestrator.sandbox.subprocess_sandbox import (
    SubprocessProcess,
    SubprocessSandbox,
)
from selffork_shared.config import SandboxConfig
from selffork_shared.errors import SandboxExecError


def test_init_validates_mode() -> None:
    cfg = SandboxConfig(mode="docker")
    with pytest.raises(ValueError, match="subprocess"):
        SubprocessSandbox(cfg, session_id="01HJTESTABCDEFGHIJ")


def test_workspace_before_spawn_raises(tmp_path: Path) -> None:
    cfg = SandboxConfig(mode="subprocess", workspace_root=str(tmp_path))
    sb = SubprocessSandbox(cfg, session_id="01HJTESTBEFORESPAWN")
    with pytest.raises(SandboxExecError):
        _ = sb.workspace_path


@pytest.mark.asyncio
async def test_spawn_creates_workspace(tmp_path: Path) -> None:
    cfg = SandboxConfig(mode="subprocess", workspace_root=str(tmp_path))
    sb = SubprocessSandbox(cfg, session_id="01HJTESTSPAWN0123456")
    await sb.spawn()
    workspace = Path(sb.workspace_path)
    assert workspace.is_dir()
    assert workspace.name == "01HJTESTSPAWN0123456"
    assert sb.host_workspace_path == sb.workspace_path
    await sb.teardown()


@pytest.mark.asyncio
async def test_spawn_idempotent(tmp_path: Path) -> None:
    cfg = SandboxConfig(mode="subprocess", workspace_root=str(tmp_path))
    sb = SubprocessSandbox(cfg, session_id="01HJTESTIDEMPOTENT01")
    await sb.spawn()
    workspace_first = sb.workspace_path
    await sb.spawn()
    assert sb.workspace_path == workspace_first
    await sb.teardown()


@pytest.mark.asyncio
async def test_exec_before_spawn_raises(tmp_path: Path) -> None:
    cfg = SandboxConfig(mode="subprocess", workspace_root=str(tmp_path))
    sb = SubprocessSandbox(cfg, session_id="01HJTESTNOSPAWN12345")
    with pytest.raises(SandboxExecError):
        await sb.exec(["echo", "hello"])


@pytest.mark.asyncio
async def test_exec_runs_command_and_captures_stdout(tmp_path: Path) -> None:
    cfg = SandboxConfig(mode="subprocess", workspace_root=str(tmp_path))
    sb = SubprocessSandbox(cfg, session_id="01HJTESTECHO12345678")
    await sb.spawn()
    proc = await sb.exec(["echo", "hello-from-sandbox"])
    assert isinstance(proc, SubprocessProcess)
    assert proc.pid > 0
    captured = b""
    async for line in proc.stdout:
        captured += line
    code = await proc.wait()
    assert code == 0
    assert b"hello-from-sandbox" in captured
    await sb.teardown()


@pytest.mark.asyncio
async def test_exec_uses_workspace_as_default_cwd(tmp_path: Path) -> None:
    cfg = SandboxConfig(mode="subprocess", workspace_root=str(tmp_path))
    sb = SubprocessSandbox(cfg, session_id="01HJTESTCWDDEFAULT12")
    await sb.spawn()
    proc = await sb.exec(["pwd"])
    captured = b""
    async for line in proc.stdout:
        captured += line
    code = await proc.wait()
    assert code == 0
    # macOS may resolve /var/... to /private/var/...; compare resolved paths.
    expected = Path(sb.workspace_path).resolve()
    actual = Path(captured.strip().decode("utf-8")).resolve()
    assert actual == expected
    await sb.teardown()


@pytest.mark.asyncio
async def test_exec_passes_env(tmp_path: Path) -> None:
    cfg = SandboxConfig(mode="subprocess", workspace_root=str(tmp_path))
    sb = SubprocessSandbox(cfg, session_id="01HJTESTENVSCOPED123")
    await sb.spawn()
    proc = await sb.exec(
        ["sh", "-c", "echo $SELFFORK_TEST_VAR"],
        env={"SELFFORK_TEST_VAR": "hello-env"},
    )
    captured = b""
    async for line in proc.stdout:
        captured += line
    code = await proc.wait()
    assert code == 0
    assert b"hello-env" in captured
    await sb.teardown()


@pytest.mark.asyncio
async def test_teardown_kills_long_running_children(tmp_path: Path) -> None:
    cfg = SandboxConfig(mode="subprocess", workspace_root=str(tmp_path))
    sb = SubprocessSandbox(cfg, session_id="01HJTESTKILLCHILD123")
    await sb.spawn()
    proc = await sb.exec(["sleep", "30"])
    pid = proc.pid
    await sb.teardown()
    code = await asyncio.wait_for(proc.wait(), timeout=5)
    assert code != 0, f"sleep child (pid {pid}) did not die after teardown"


@pytest.mark.asyncio
async def test_teardown_idempotent(tmp_path: Path) -> None:
    cfg = SandboxConfig(mode="subprocess", workspace_root=str(tmp_path))
    sb = SubprocessSandbox(cfg, session_id="01HJTESTTEARDOWNIDEM")
    await sb.spawn()
    await sb.teardown()
    await sb.teardown()  # no-op
