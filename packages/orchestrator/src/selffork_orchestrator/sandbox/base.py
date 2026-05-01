"""Sandbox / SandboxProcess ABCs.

A :class:`Sandbox` is an isolated execution environment (subprocess or
Docker) where opencode runs. A :class:`SandboxProcess` is a handle to a
single process spawned inside one — exposes pid, stdout/stderr line
streams, ``wait()``, and ``kill()``.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.2.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping

from selffork_shared.config import SandboxConfig

__all__ = ["Sandbox", "SandboxProcess"]


class SandboxProcess(ABC):
    """Handle to a process running inside a :class:`Sandbox`."""

    @property
    @abstractmethod
    def pid(self) -> int:
        """OS PID of the host-side process.

        For SubprocessSandbox: the actual child PID.
        For DockerSandbox: the PID of the host-side ``docker exec`` wrapper
        (NOT the in-container process). Killing this wrapper does not kill
        the in-container process; rely on :meth:`Sandbox.teardown` for that.
        """

    @property
    @abstractmethod
    def stdout(self) -> AsyncIterator[bytes]:
        """Async iterator over stdout lines (newline-terminated bytes)."""

    @property
    @abstractmethod
    def stderr(self) -> AsyncIterator[bytes]:
        """Async iterator over stderr lines."""

    @abstractmethod
    async def wait(self) -> int:
        """Block until the process exits, return its exit code."""

    @abstractmethod
    async def kill(self, grace_seconds: float = 1.0) -> None:
        """SIGTERM, wait grace, SIGKILL fallback. Idempotent."""


class Sandbox(ABC):
    """Isolated execution environment for an autonomous CLI agent."""

    @abstractmethod
    def __init__(self, config: SandboxConfig, session_id: str) -> None:
        """Initialise from config + a unique session id.

        Implementations must validate that ``config.mode`` matches the
        mode they implement, and raise :class:`ValueError` otherwise.
        """

    @abstractmethod
    async def spawn(self) -> None:
        """Create the isolated environment.

        After this returns, :meth:`exec` may be called. Idempotent.

        Raises:
            selffork_shared.errors.SandboxSpawnError: env could not be
                created (workspace dir, container start, etc.).
        """

    @abstractmethod
    async def exec(
        self,
        command: list[str],
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxProcess:
        """Run a process inside the sandbox; returns a streaming handle.

        Multiple concurrent ``exec()`` calls are allowed; the sandbox
        tracks them and kills any that are still alive at teardown.

        Raises:
            selffork_shared.errors.SandboxExecError: subprocess could not
                be spawned, or the sandbox is not yet ``spawn()`` ed.
        """

    @abstractmethod
    async def teardown(self) -> None:
        """Stop all running processes, clean up resources.

        Idempotent. Always called on session end (success or failure)
        via try/finally in the orchestrator.
        """

    @property
    @abstractmethod
    def workspace_path(self) -> str:
        """Project workdir path **as seen from inside the sandbox**.

        For SubprocessSandbox: equals :attr:`host_workspace_path` (no
        re-mapping; cwd is the host path).
        For DockerSandbox: bind-mount target inside the container,
        typically ``/workspace``.
        """

    @property
    @abstractmethod
    def host_workspace_path(self) -> str:
        """Project workdir path on the **host filesystem**.

        Equal to :attr:`workspace_path` in subprocess mode.
        """
