"""Sandbox adapters — subprocess and Docker isolation modes.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.2.
"""

from __future__ import annotations

from selffork_orchestrator.sandbox.base import Sandbox, SandboxProcess
from selffork_orchestrator.sandbox.docker_sandbox import DockerProcess, DockerSandbox
from selffork_orchestrator.sandbox.factory import build_sandbox
from selffork_orchestrator.sandbox.subprocess_sandbox import (
    SubprocessProcess,
    SubprocessSandbox,
)

__all__ = [
    "DockerProcess",
    "DockerSandbox",
    "Sandbox",
    "SandboxProcess",
    "SubprocessProcess",
    "SubprocessSandbox",
    "build_sandbox",
]
