"""Tests for :func:`build_sandbox`."""

from __future__ import annotations

from selffork_orchestrator.sandbox.docker_sandbox import DockerSandbox
from selffork_orchestrator.sandbox.factory import build_sandbox
from selffork_orchestrator.sandbox.subprocess_sandbox import SubprocessSandbox
from selffork_shared.config import SandboxConfig


def test_subprocess_resolved() -> None:
    cfg = SandboxConfig(mode="subprocess")
    sb = build_sandbox(cfg, session_id="01HJTESTFACTORYSUBPR")
    assert isinstance(sb, SubprocessSandbox)


def test_docker_resolved() -> None:
    cfg = SandboxConfig(mode="docker")
    sb = build_sandbox(cfg, session_id="01HJTESTFACTORYDOCKE")
    assert isinstance(sb, DockerSandbox)
