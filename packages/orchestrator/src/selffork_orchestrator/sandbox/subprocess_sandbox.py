"""SubprocessSandbox — Mac local-dev mode.

Each sandbox owns a workspace directory under
``<workspace_root>/<session_id>/`` and tracks every child it spawns.
:meth:`exec` ``asyncio.create_subprocess_exec`` 's a process in a new
session group with the given env and cwd; :meth:`teardown` SIGTERMs
all live children (SIGKILL after a grace window).

Inspired by patterns from
`prior art in the agentic-CLI orchestration space`
(SIGTERM → grace → SIGKILL) and
`prior art in the agentic-CLI orchestration space` (filesystem layout).

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.2, §13.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from collections.abc import AsyncIterator, Mapping
from pathlib import Path

from selffork_orchestrator.sandbox.base import Sandbox, SandboxProcess
from selffork_shared.config import SandboxConfig
from selffork_shared.errors import SandboxExecError, SandboxSpawnError
from selffork_shared.logging import get_logger

__all__ = ["SubprocessProcess", "SubprocessSandbox"]

_log = get_logger(__name__)

# Default grace window passed to ``kill()`` when teardown loops over children.
_TEARDOWN_GRACE_SECONDS = 1.0


def _ensure_workspace_dirs(workspace_root: str, session_id: str) -> Path:
    """Sync helper for ``Sandbox.spawn`` — runs on a thread to keep the loop free.

    Resolves ``~`` in the configured root, creates root + per-session
    workspace directories (idempotent), returns the workspace path.
    """
    root = Path(workspace_root).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    workspace = root / session_id
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


class SubprocessProcess(SandboxProcess):
    """Handle to an asyncio subprocess running on the host."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc

    @property
    def pid(self) -> int:
        return self._proc.pid

    @property
    def stdout(self) -> AsyncIterator[bytes]:
        if self._proc.stdout is None:
            raise SandboxExecError("stdout was not piped")
        return self._proc.stdout

    @property
    def stderr(self) -> AsyncIterator[bytes]:
        if self._proc.stderr is None:
            raise SandboxExecError("stderr was not piped")
        return self._proc.stderr

    async def wait(self) -> int:
        return await self._proc.wait()

    async def kill(self, grace_seconds: float = 1.0) -> None:
        if self._proc.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError, OSError):
            os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=grace_seconds)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError, OSError):
                os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)


class SubprocessSandbox(Sandbox):
    """Subprocess-based isolation for local Mac dev.

    Workspace is a plain directory under ``<workspace_root>/<session_id>/``.
    Processes are spawned in a new session group (``start_new_session=True``)
    so SIGTERM/SIGKILL on the group hits all descendants.
    """

    def __init__(self, config: SandboxConfig, session_id: str) -> None:
        if config.mode != "subprocess":
            raise ValueError(
                f"SubprocessSandbox requires mode='subprocess', got {config.mode!r}",
            )
        self._config = config
        self._session_id = session_id
        self._workspace: Path | None = None
        self._children: list[SubprocessProcess] = []
        self._spawned = False

    @property
    def workspace_path(self) -> str:
        if self._workspace is None:
            raise SandboxExecError("workspace_path accessed before spawn()")
        return str(self._workspace)

    @property
    def host_workspace_path(self) -> str:
        return self.workspace_path

    async def spawn(self) -> None:
        if self._spawned:
            return
        try:
            workspace = await asyncio.to_thread(
                _ensure_workspace_dirs,
                self._config.workspace_root,
                self._session_id,
            )
        except OSError as exc:
            raise SandboxSpawnError(f"failed to create workspace: {exc}") from exc
        self._workspace = workspace
        self._spawned = True
        _log.info(
            "sandbox_spawn",
            mode="subprocess",
            workspace=str(workspace),
            session_id=self._session_id,
        )

    async def exec(
        self,
        command: list[str],
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxProcess:
        if not self._spawned or self._workspace is None:
            raise SandboxExecError("sandbox not spawned; call spawn() first")
        actual_cwd = cwd if cwd is not None else str(self._workspace)
        actual_env = dict(env) if env is not None else dict(os.environ)
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=actual_cwd,
                env=actual_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except (OSError, FileNotFoundError) as exc:
            raise SandboxExecError(
                f"failed to spawn process (cmd={command}): {exc}",
            ) from exc
        handle = SubprocessProcess(proc)
        self._children.append(handle)
        _log.info(
            "sandbox_exec",
            command=command,
            cwd=actual_cwd,
            pid=proc.pid,
        )
        return handle

    async def teardown(self) -> None:
        if self._children:
            await asyncio.gather(
                *(child.kill(grace_seconds=_TEARDOWN_GRACE_SECONDS) for child in self._children),
                return_exceptions=True,
            )
            self._children.clear()
        # We deliberately do NOT remove the workspace directory — the agent's
        # output lives there and the operator inspects it post-run. Cleanup
        # is the operator's responsibility.
        _log.info(
            "sandbox_teardown",
            mode="subprocess",
            workspace=str(self._workspace) if self._workspace else None,
        )
        self._spawned = False
