"""macOS sandbox-exec backend (M5 — ADR-005 §M5-D1).

Wraps :class:`SubprocessSandbox` by prepending ``sandbox-exec -f <profile>`` to
every spawned command. SBPL profile is generated lazily on first ``exec`` and
cached for the session lifetime under the workspace directory.

References:
* `michaelneale/agent-seatbelt-sandbox <https://github.com/michaelneale/agent-seatbelt-sandbox>`_
* Apple Sandbox Guide v1.0 (fG!, 2011)

Note: ``sandbox-exec`` is marked deprecated by Apple but remains the default
profile-driven sandbox tool on macOS through the foreseeable future. M6 may
migrate to App Sandbox entitlements once the body daemon ships as a notarized
``.app`` bundle.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from selffork_orchestrator.sandbox.base import SandboxProcess
from selffork_orchestrator.sandbox.subprocess_sandbox import SubprocessSandbox
from selffork_shared.config import SandboxConfig
from selffork_shared.errors import SandboxExecError

__all__ = ["SeatbeltSandbox", "build_sbpl_profile"]


_DEFAULT_PROFILE_TEMPLATE = """\
(version 1)
(deny default)

;; Always allow read-only access to system frameworks + dyld cache.
(allow file-read*
    (subpath "/usr")
    (subpath "/System")
    (subpath "/Library/Frameworks")
    (subpath "/Library/Developer")
    (subpath "/private/var/db/dyld")
    (literal "/dev/null")
    (literal "/dev/random")
    (literal "/dev/urandom"))

;; Allow ``/etc/resolv.conf`` and friends so DNS works.
(allow file-read*
    (subpath "/etc"))

;; Workspace + selffork data dir are read-write.
(allow file*
    (subpath "{workspace}")
    (subpath "{selffork_home}"))

;; tmp space.
(allow file*
    (subpath "/private/tmp")
    (subpath "/private/var/folders"))

;; Process metadata (so the agent can introspect itself / children).
(allow process-info* (target self))
(allow process-fork)
(allow process-exec
    (subpath "/usr/bin")
    (subpath "/usr/local/bin")
    (subpath "/opt/homebrew")
    (subpath "{workspace}")
    (subpath "{selffork_home}"))

;; HTTPS by default; let extra rules expand the egress envelope.
(allow network-outbound
    (remote tcp "*:443")
    (remote tcp "*:80"))

;; Caller-defined extra rules (allowlist URLs, syscalls, file subpaths).
{extra_rules}
"""


def build_sbpl_profile(
    *,
    workspace: str,
    selffork_home: str,
    extra_rules: str = "",
) -> str:
    """Render an SBPL profile string ready for ``sandbox-exec -p`` or ``-f``.

    ``extra_rules`` is concatenated verbatim — caller is responsible for valid
    SBPL syntax (e.g. ``(allow network-outbound (remote tcp "github.com:443"))``).
    """
    return _DEFAULT_PROFILE_TEMPLATE.format(
        workspace=workspace,
        selffork_home=selffork_home,
        extra_rules=extra_rules,
    )


class SeatbeltSandbox(SubprocessSandbox):
    """SubprocessSandbox + ``sandbox-exec`` wrapper.

    The profile is materialised once per session at
    ``<workspace>/.selffork/seatbelt.sb``. ``config.docker_run_extra_args`` is
    repurposed as opaque extra SBPL rules (``(allow ...)`` lines) appended to
    the default template.
    """

    def __init__(self, config: SandboxConfig, session_id: str) -> None:
        if config.mode != "seatbelt":
            raise ValueError(
                f"SeatbeltSandbox requires mode='seatbelt', got {config.mode!r}",
            )
        # SubprocessSandbox checks ``mode == 'subprocess'`` — bypass by mutating
        # a copy we keep, then call its constructor with a relaxed view.
        relaxed = config.model_copy(update={"mode": "subprocess"})
        super().__init__(relaxed, session_id)
        self._real_mode = config.mode
        self._profile_path: Path | None = None
        self._extra_rules = "\n".join(
            line for line in (config.docker_run_extra_args or []) if line.strip()
        )

    async def _materialise_profile(self) -> Path:
        if self._profile_path is not None:
            return self._profile_path
        if self._workspace is None:
            raise SandboxExecError("workspace not spawned; cannot write profile")
        sf_home = str(Path("~/.selffork").expanduser())
        profile = build_sbpl_profile(
            workspace=str(self._workspace),
            selffork_home=sf_home,
            extra_rules=self._extra_rules,
        )
        path = self._workspace / ".selffork" / "seatbelt.sb"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(profile, encoding="utf-8")
        self._profile_path = path
        return path

    async def exec(
        self,
        command: list[str],
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxProcess:
        profile = await self._materialise_profile()
        wrapped = ["sandbox-exec", "-f", str(profile), *command]
        return await super().exec(wrapped, env=env, cwd=cwd)
