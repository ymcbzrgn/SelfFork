"""Unit tests for :class:`DockerSandbox` that don't require Docker.

Tests that actually spawn a container live under ``tests/e2e/`` and are
gated by ``@pytest.mark.real_docker``.
"""

from __future__ import annotations

import pytest

from selffork_orchestrator.sandbox.docker_sandbox import DockerSandbox
from selffork_shared.config import SandboxConfig
from selffork_shared.errors import SandboxExecError


def test_init_validates_mode() -> None:
    cfg = SandboxConfig(mode="subprocess")
    with pytest.raises(ValueError, match="docker"):
        DockerSandbox(cfg, session_id="01HJTESTDOCKERMODE12")


def test_workspace_path_is_container_workspace() -> None:
    cfg = SandboxConfig(mode="docker")
    sb = DockerSandbox(cfg, session_id="01HJTESTDOCKERWSPATH")
    assert sb.workspace_path == "/workspace"


def test_host_workspace_before_spawn_raises() -> None:
    cfg = SandboxConfig(mode="docker")
    sb = DockerSandbox(cfg, session_id="01HJTESTDOCKERHOSTWS")
    with pytest.raises(SandboxExecError):
        _ = sb.host_workspace_path


def test_container_id_none_before_spawn() -> None:
    cfg = SandboxConfig(mode="docker")
    sb = DockerSandbox(cfg, session_id="01HJTESTDOCKERCIDNON")
    assert sb.container_id is None


@pytest.mark.asyncio
async def test_exec_before_spawn_raises() -> None:
    cfg = SandboxConfig(mode="docker")
    sb = DockerSandbox(cfg, session_id="01HJTESTDOCKEREXECNS")
    with pytest.raises(SandboxExecError):
        await sb.exec(["echo", "hi"])


@pytest.mark.asyncio
async def test_teardown_no_container_is_noop() -> None:
    cfg = SandboxConfig(mode="docker")
    sb = DockerSandbox(cfg, session_id="01HJTESTDOCKERTDNOOP")
    # No spawn — teardown should silently succeed.
    await sb.teardown()
    assert sb.container_id is None
