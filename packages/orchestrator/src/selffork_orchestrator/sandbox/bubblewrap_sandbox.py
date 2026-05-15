"""Linux bubblewrap backend (M5 — ADR-005 §M5-D1).

Wraps :class:`SubprocessSandbox` by prepending ``bwrap`` with a deny-default
mount + namespace policy. Network is shared with host by default; egress
allowlisting is delegated to a separate proxy layer (see Anthropic Claude
Code's "socat allowlist" pattern).

References:
* `containers/bubblewrap <https://github.com/containers/bubblewrap>`_
* Anthropic Engineering — Claude Code Sandboxing (2025-11)
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from selffork_orchestrator.sandbox.base import SandboxProcess
from selffork_orchestrator.sandbox.subprocess_sandbox import SubprocessSandbox
from selffork_shared.config import SandboxConfig

__all__ = ["BubblewrapSandbox", "build_bwrap_args"]


def build_bwrap_args(
    *,
    workspace: str,
    selffork_home: str,
    share_net: bool = True,
    extra_args: list[str] | None = None,
) -> list[str]:
    """Return the ``bwrap`` argument prefix (no command tail).

    Default policy:
    * ``--unshare-all`` then re-share network when ``share_net=True``.
    * ``/`` mounted read-only; tmp / dev are bwrap-managed.
    * Workspace + ``~/.selffork`` are bind-mounted read-write.
    """
    args: list[str] = [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--ro-bind", "/", "/",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--bind", workspace, workspace,
        "--bind", selffork_home, selffork_home,
        "--setenv", "HOME", selffork_home,
    ]
    if share_net:
        args.append("--share-net")
    if extra_args:
        args.extend(extra_args)
    args.append("--")
    return args


class BubblewrapSandbox(SubprocessSandbox):
    """SubprocessSandbox + ``bwrap`` wrapper for Linux daemon hosts."""

    def __init__(self, config: SandboxConfig, session_id: str) -> None:
        if config.mode != "bubblewrap":
            raise ValueError(
                f"BubblewrapSandbox requires mode='bubblewrap', got {config.mode!r}",
            )
        relaxed = config.model_copy(update={"mode": "subprocess"})
        super().__init__(relaxed, session_id)
        self._real_mode = config.mode
        self._extra_args = list(config.docker_run_extra_args or [])

    def _bwrap_prefix(self) -> list[str]:
        if self._workspace is None:
            raise RuntimeError("workspace not spawned")
        sf_home = str(Path("~/.selffork").expanduser())
        return build_bwrap_args(
            workspace=str(self._workspace),
            selffork_home=sf_home,
            share_net=True,
            extra_args=self._extra_args,
        )

    async def exec(
        self,
        command: list[str],
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxProcess:
        wrapped = [*self._bwrap_prefix(), *command]
        return await super().exec(wrapped, env=env, cwd=cwd)
