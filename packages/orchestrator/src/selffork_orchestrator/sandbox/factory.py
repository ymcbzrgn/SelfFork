"""Backend → implementation resolver for :class:`Sandbox`."""

from __future__ import annotations

from collections.abc import Mapping

from selffork_orchestrator.sandbox.base import Sandbox
from selffork_orchestrator.sandbox.docker_sandbox import DockerSandbox
from selffork_orchestrator.sandbox.subprocess_sandbox import SubprocessSandbox
from selffork_shared.config import SandboxConfig

__all__ = ["build_sandbox"]

_BACKENDS: Mapping[str, type[Sandbox]] = {
    "subprocess": SubprocessSandbox,
    "docker": DockerSandbox,
}


def build_sandbox(config: SandboxConfig, session_id: str) -> Sandbox:
    """Return a fresh :class:`Sandbox` instance for ``config.mode``."""
    cls = _BACKENDS.get(config.mode)
    if cls is None:
        # Unreachable: ``config.mode`` is a Pydantic Literal validated at boot.
        raise ValueError(f"unknown sandbox mode: {config.mode!r}")
    return cls(config, session_id)
