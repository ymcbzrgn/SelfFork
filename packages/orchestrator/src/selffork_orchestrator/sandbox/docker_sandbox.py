"""DockerSandbox — server-side mode with full container isolation.

Each session = one Docker container. The host workspace dir
(``<workspace_root>/<session_id>/``) is bind-mounted to a fixed in-container
path (``/workspace``).

Lifecycle:

* :meth:`spawn` runs ``docker run --rm -d --name selffork-<sid>
  -v <host>:/workspace ... <image> sleep infinity`` to start a long-lived
  container we can ``docker exec`` into.
* :meth:`exec` runs ``docker exec [-e KEY=VAL]... [-w cwd] <cid> <cmd>``.
* :meth:`teardown` runs ``docker stop -t <secs> <cid>``; ``--rm`` removes
  the container.

Pattern reference: `prior art in the agentic-CLI orchestration space`
and ``CUSTOM_CONFIGURATIONS.md:14-45`` for port maps, bind mounts, env
config surface.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.2, §13.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Mapping
from pathlib import Path

from selffork_orchestrator.sandbox.base import Sandbox, SandboxProcess
from selffork_shared.config import SandboxConfig
from selffork_shared.errors import SandboxExecError, SandboxSpawnError
from selffork_shared.logging import get_logger

__all__ = ["DockerProcess", "DockerSandbox"]

_log = get_logger(__name__)

# Path inside the container where the host workspace is mounted.
_CONTAINER_WORKSPACE = "/workspace"
# Stop timeout passed to ``docker stop -t``.
_DOCKER_STOP_TIMEOUT_SECONDS = 5
# Bytes of stderr to surface when ``docker run`` fails.
_STDERR_PREVIEW_CHARS = 500


def _ensure_host_workspace_dirs(workspace_root: str, session_id: str) -> Path:
    """Sync helper for ``DockerSandbox.spawn`` — runs on a thread.

    Identical body to ``subprocess_sandbox._ensure_workspace_dirs``;
    duplicated rather than imported across files to keep the sandbox
    submodules independent (no inter-impl coupling).
    """
    root = Path(workspace_root).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    workspace = root / session_id
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


class DockerProcess(SandboxProcess):
    """Handle to a process running via ``docker exec`` against a container."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc

    @property
    def pid(self) -> int:
        # Host PID of the ``docker exec`` wrapper, not the in-container PID.
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
        # Killing the host-side ``docker exec`` does NOT kill the in-container
        # process. For MVP this is acceptable — :meth:`Sandbox.teardown` runs
        # ``docker stop`` which terminates the container and all its children.
        if self._proc.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError, OSError):
            self._proc.terminate()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=grace_seconds)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError, OSError):
                self._proc.kill()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)


class DockerSandbox(Sandbox):
    """Docker-container isolation for server-side multi-project mode."""

    def __init__(self, config: SandboxConfig, session_id: str) -> None:
        if config.mode != "docker":
            raise ValueError(
                f"DockerSandbox requires mode='docker', got {config.mode!r}",
            )
        self._config = config
        self._session_id = session_id
        self._host_workspace: Path | None = None
        self._container_id: str | None = None
        self._children: list[DockerProcess] = []

    @property
    def workspace_path(self) -> str:
        return _CONTAINER_WORKSPACE

    @property
    def host_workspace_path(self) -> str:
        if self._host_workspace is None:
            raise SandboxExecError("host_workspace_path accessed before spawn()")
        return str(self._host_workspace)

    @property
    def container_id(self) -> str | None:
        """Container ID set by :meth:`spawn`. ``None`` before spawn / after teardown."""
        return self._container_id

    async def spawn(self) -> None:
        if self._container_id is not None:
            return
        try:
            workspace = await asyncio.to_thread(
                _ensure_host_workspace_dirs,
                self._config.workspace_root,
                self._session_id,
            )
        except OSError as exc:
            raise SandboxSpawnError(f"failed to create host workspace: {exc}") from exc
        self._host_workspace = workspace

        cmd = [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            f"selffork-{self._session_id}",
            "-v",
            f"{workspace}:{_CONTAINER_WORKSPACE}",
            "-w",
            _CONTAINER_WORKSPACE,
            *self._config.docker_run_extra_args,
            self._config.docker_image,
            "sleep",
            "infinity",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        except (OSError, FileNotFoundError) as exc:
            raise SandboxSpawnError(f"failed to invoke docker (cmd={cmd}): {exc}") from exc
        if proc.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace").strip()[:_STDERR_PREVIEW_CHARS]
            raise SandboxSpawnError(
                f"docker run failed (exit {proc.returncode}): {stderr_text}",
            )

        self._container_id = stdout.decode("utf-8", errors="replace").strip()
        _log.info(
            "sandbox_spawn",
            mode="docker",
            workspace=str(workspace),
            container_id=self._container_id,
            image=self._config.docker_image,
        )

    async def exec(
        self,
        command: list[str],
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxProcess:
        if self._container_id is None:
            raise SandboxExecError("sandbox not spawned; call spawn() first")
        docker_cmd: list[str] = ["docker", "exec"]
        if env is not None:
            for key, value in env.items():
                docker_cmd.extend(["-e", f"{key}={value}"])
        if cwd is not None:
            docker_cmd.extend(["-w", cwd])
        docker_cmd.append(self._container_id)
        docker_cmd.extend(command)
        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, FileNotFoundError) as exc:
            raise SandboxExecError(f"failed to docker-exec (cmd={docker_cmd}): {exc}") from exc
        handle = DockerProcess(proc)
        self._children.append(handle)
        _log.info(
            "sandbox_exec",
            command=command,
            container_id=self._container_id,
            pid=proc.pid,
        )
        return handle

    async def teardown(self) -> None:
        if self._children:
            await asyncio.gather(
                *(child.kill() for child in self._children),
                return_exceptions=True,
            )
            self._children.clear()
        if self._container_id is not None:
            stop_cmd = [
                "docker",
                "stop",
                "-t",
                str(_DOCKER_STOP_TIMEOUT_SECONDS),
                self._container_id,
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *stop_cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    _log.warning(
                        "sandbox_teardown_docker_stop_failed",
                        container_id=self._container_id,
                        exit_code=proc.returncode,
                        stderr=stderr.decode("utf-8", errors="replace").strip(),
                    )
            except (OSError, FileNotFoundError) as exc:
                _log.warning(
                    "sandbox_teardown_docker_stop_error",
                    container_id=self._container_id,
                    error=str(exc),
                )
        _log.info(
            "sandbox_teardown",
            mode="docker",
            container_id=self._container_id,
        )
        self._container_id = None
