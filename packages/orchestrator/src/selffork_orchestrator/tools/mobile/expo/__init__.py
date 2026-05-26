"""Expo dev-workflow tools — dev server / EAS / metro / run / install / doctor (12 tools).

S-ToolFleet Faz 1. All deferred (operator dev-time use, not part of the
agentic mobile observe→act loop). Subprocess wrappers around the
``expo`` and ``eas`` CLIs; the active project directory comes from
``SELFFORK_EXPO_PROJECT_DIR`` env or each tool's explicit ``project_dir``
arg.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.body._internal import _emit_audit, _gate

__all__ = [
    "ExpoDevStartArgs",
    "ExpoDevStopArgs",
    "ExpoDoctorArgs",
    "ExpoEasBuildArgs",
    "ExpoEasSubmitArgs",
    "ExpoExportArgs",
    "ExpoInstallArgs",
    "ExpoLogsCaptureArgs",
    "ExpoMetroReloadArgs",
    "ExpoPublishArgs",
    "ExpoRunAndroidArgs",
    "ExpoRunIosArgs",
    "build_expo_tools",
]


# Module-level state for the background ``expo start`` process so
# ``expo_dev_stop`` can terminate it. Keyed by project_dir so multiple
# projects can run in parallel. Process-wide singleton — operator-level
# tool, not shared across sessions.
_DEV_PROCS: dict[str, asyncio.subprocess.Process] = {}


def _resolve_project_dir(project_dir: str | None) -> Path:
    if project_dir:
        return Path(project_dir).expanduser()
    env = os.environ.get("SELFFORK_EXPO_PROJECT_DIR")
    if env:
        return Path(env).expanduser()
    return Path.cwd()


class ExpoDevStartArgs(ToolArgs):
    project_dir: str | None = None
    port: int = Field(default=8081, ge=1024, le=65535)
    clear_cache: bool = False


class ExpoDevStopArgs(ToolArgs):
    project_dir: str | None = None


class ExpoMetroReloadArgs(ToolArgs):
    project_dir: str | None = None


class ExpoLogsCaptureArgs(ToolArgs):
    project_dir: str | None = None
    max_lines: int = Field(default=200, ge=1, le=10_000)


class ExpoEasBuildArgs(ToolArgs):
    project_dir: str | None = None
    platform: Literal["ios", "android", "all"] = "all"
    profile: str = "preview"
    local: bool = False


class ExpoEasSubmitArgs(ToolArgs):
    project_dir: str | None = None
    platform: Literal["ios", "android"] = "ios"
    profile: str = "production"


class ExpoPublishArgs(ToolArgs):
    project_dir: str | None = None
    channel: str | None = None


class ExpoExportArgs(ToolArgs):
    project_dir: str | None = None
    platform: Literal["ios", "android", "all"] = "all"
    output_dir: str = "dist"


class ExpoRunIosArgs(ToolArgs):
    project_dir: str | None = None
    device: str | None = None


class ExpoRunAndroidArgs(ToolArgs):
    project_dir: str | None = None
    variant: str = "debug"


class ExpoInstallArgs(ToolArgs):
    project_dir: str | None = None
    package: str = Field(min_length=1, max_length=255)


class ExpoDoctorArgs(ToolArgs):
    project_dir: str | None = None


async def _run_subprocess(
    cmd: list[str], cwd: Path, *, timeout: float | None = 300.0,  # noqa: ASYNC109
) -> dict[str, Any]:
    """Run a subprocess capturing stdout/stderr with timeout."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return {
            "status": "timeout",
            "timeout_seconds": timeout,
            "stdout": "",
            "stderr": "process timed out",
        }
    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "returncode": proc.returncode,
        "stdout": stdout.decode(errors="replace")[:8192],
        "stderr": stderr.decode(errors="replace")[:8192],
    }


async def _expo_gate_and_run(
    ctx: ToolContext,
    *,
    action_type: str,
    target_uri: str | None,
    args_summary: dict[str, Any],
    cmd: list[str],
    cwd: Path,
    timeout: float | None = 600.0,  # noqa: ASYNC109
) -> dict[str, Any]:
    approved, denied = await _gate(
        ctx,
        action_type=action_type,
        target_uri=target_uri,
        args_summary=args_summary,
    )
    if not approved:
        return denied
    _emit_audit(
        ctx,
        "body.action.invoke",
        {"action_type": action_type, "target_uri_redacted": target_uri},
    )
    result = await _run_subprocess(cmd, cwd, timeout=timeout)
    _emit_audit(
        ctx,
        "body.action.executed" if result["status"] == "ok" else "body.action.failed",
        {
            "action_type": action_type,
            "target_uri_redacted": target_uri,
            "returncode": result.get("returncode"),
        },
    )
    return result


async def _expo_dev_start(ctx: ToolContext, args: ExpoDevStartArgs) -> dict[str, Any]:
    project_dir = _resolve_project_dir(args.project_dir)
    key = str(project_dir)
    if key in _DEV_PROCS:
        return {"status": "already_running", "project_dir": key}

    approved, denied = await _gate(
        ctx,
        action_type="expo.dev_start",
        target_uri=str(project_dir),
        args_summary={
            "project_dir": str(project_dir),
            "port": args.port,
            "clear_cache": args.clear_cache,
        },
    )
    if not approved:
        return denied

    cmd = ["npx", "expo", "start", "--port", str(args.port)]
    if args.clear_cache:
        cmd.append("--clear")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(project_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    _DEV_PROCS[key] = proc
    return {"status": "started", "pid": proc.pid, "project_dir": key, "port": args.port}


async def _expo_dev_stop(ctx: ToolContext, args: ExpoDevStopArgs) -> dict[str, Any]:
    project_dir = _resolve_project_dir(args.project_dir)
    key = str(project_dir)
    proc = _DEV_PROCS.pop(key, None)
    if proc is None:
        return {"status": "not_running", "project_dir": key}
    approved, denied = await _gate(
        ctx,
        action_type="expo.dev_stop",
        target_uri=key,
        args_summary={"project_dir": key},
    )
    if not approved:
        _DEV_PROCS[key] = proc  # restore — gate denied
        return denied
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=10.0)
    except TimeoutError:
        proc.kill()
        await proc.wait()
    return {"status": "stopped", "project_dir": key, "pid": proc.pid}


async def _expo_metro_reload(
    ctx: ToolContext, args: ExpoMetroReloadArgs,
) -> dict[str, Any]:
    project_dir = _resolve_project_dir(args.project_dir)
    # Metro reload trigger via DevServer HTTP endpoint
    return await _expo_gate_and_run(
        ctx,
        action_type="expo.metro_reload",
        target_uri=str(project_dir),
        args_summary={"project_dir": str(project_dir)},
        cmd=["curl", "-s", "-X", "POST", "http://localhost:8081/reload"],
        cwd=project_dir,
        timeout=10.0,
    )


async def _expo_logs_capture(
    ctx: ToolContext, args: ExpoLogsCaptureArgs,
) -> dict[str, Any]:
    project_dir = _resolve_project_dir(args.project_dir)
    # Read the metro log if present
    log_path = project_dir / ".expo" / "metro.log"

    approved, denied = await _gate(
        ctx,
        action_type="expo.logs_capture",
        target_uri=str(log_path),
        args_summary={
            "project_dir": str(project_dir),
            "max_lines": args.max_lines,
        },
    )
    if not approved:
        return denied
    if not log_path.is_file():
        return {"status": "not_found", "path": str(log_path)}
    lines = log_path.read_text(errors="replace").splitlines()[-args.max_lines:]
    text = "\n".join(lines)
    return {"status": "ok", "text_len": len(text), "preview": text[:8192]}


async def _expo_eas_build(
    ctx: ToolContext, args: ExpoEasBuildArgs,
) -> dict[str, Any]:
    project_dir = _resolve_project_dir(args.project_dir)
    cmd = [
        "npx", "eas", "build",
        "--profile", args.profile,
        "--platform", args.platform,
        "--non-interactive",
    ]
    if args.local:
        cmd.append("--local")
    return await _expo_gate_and_run(
        ctx,
        action_type="expo.eas_build",
        target_uri=str(project_dir),
        args_summary={
            "platform": args.platform,
            "profile": args.profile,
            "local": args.local,
        },
        cmd=cmd,
        cwd=project_dir,
        timeout=3_600.0,  # 1h cap for EAS local build
    )


async def _expo_eas_submit(
    ctx: ToolContext, args: ExpoEasSubmitArgs,
) -> dict[str, Any]:
    project_dir = _resolve_project_dir(args.project_dir)
    cmd = [
        "npx", "eas", "submit",
        "--profile", args.profile,
        "--platform", args.platform,
        "--non-interactive",
    ]
    return await _expo_gate_and_run(
        ctx,
        action_type="expo.eas_submit",
        target_uri=str(project_dir),
        args_summary={"platform": args.platform, "profile": args.profile},
        cmd=cmd,
        cwd=project_dir,
        timeout=900.0,
    )


async def _expo_publish(ctx: ToolContext, args: ExpoPublishArgs) -> dict[str, Any]:
    project_dir = _resolve_project_dir(args.project_dir)
    cmd = ["npx", "expo", "publish", "--non-interactive"]
    if args.channel:
        cmd += ["--release-channel", args.channel]
    return await _expo_gate_and_run(
        ctx,
        action_type="expo.publish",
        target_uri=str(project_dir),
        args_summary={"channel": args.channel},
        cmd=cmd,
        cwd=project_dir,
        timeout=900.0,
    )


async def _expo_export(ctx: ToolContext, args: ExpoExportArgs) -> dict[str, Any]:
    project_dir = _resolve_project_dir(args.project_dir)
    cmd = ["npx", "expo", "export", "--platform", args.platform, "--output-dir", args.output_dir]
    return await _expo_gate_and_run(
        ctx,
        action_type="expo.export",
        target_uri=str(project_dir),
        args_summary={"platform": args.platform, "output_dir": args.output_dir},
        cmd=cmd,
        cwd=project_dir,
        timeout=900.0,
    )


async def _expo_run_ios(ctx: ToolContext, args: ExpoRunIosArgs) -> dict[str, Any]:
    project_dir = _resolve_project_dir(args.project_dir)
    cmd = ["npx", "expo", "run:ios"]
    if args.device:
        cmd += ["--device", args.device]
    return await _expo_gate_and_run(
        ctx,
        action_type="expo.run_ios",
        target_uri=str(project_dir),
        args_summary={"device": args.device},
        cmd=cmd,
        cwd=project_dir,
        timeout=900.0,
    )


async def _expo_run_android(
    ctx: ToolContext, args: ExpoRunAndroidArgs,
) -> dict[str, Any]:
    project_dir = _resolve_project_dir(args.project_dir)
    cmd = ["npx", "expo", "run:android", "--variant", args.variant]
    return await _expo_gate_and_run(
        ctx,
        action_type="expo.run_android",
        target_uri=str(project_dir),
        args_summary={"variant": args.variant},
        cmd=cmd,
        cwd=project_dir,
        timeout=900.0,
    )


async def _expo_install(ctx: ToolContext, args: ExpoInstallArgs) -> dict[str, Any]:
    project_dir = _resolve_project_dir(args.project_dir)
    cmd = ["npx", "expo", "install", args.package]
    return await _expo_gate_and_run(
        ctx,
        action_type="expo.install",
        target_uri=str(project_dir),
        args_summary={"package": args.package},
        cmd=cmd,
        cwd=project_dir,
        timeout=300.0,
    )


async def _expo_doctor(ctx: ToolContext, args: ExpoDoctorArgs) -> dict[str, Any]:
    project_dir = _resolve_project_dir(args.project_dir)
    cmd = ["npx", "expo-doctor"]
    return await _expo_gate_and_run(
        ctx,
        action_type="expo.doctor",
        target_uri=str(project_dir),
        args_summary={"project_dir": str(project_dir)},
        cmd=cmd,
        cwd=project_dir,
        timeout=180.0,
    )


def build_expo_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="expo_dev_start",
            description="Start `expo start` in the background; returns PID.",
            args_model=ExpoDevStartArgs,
            handler=_expo_dev_start,
            defer_loading=True,
        ),
        ToolSpec(
            name="expo_dev_stop",
            description="Stop the background `expo start` process for a project.",
            args_model=ExpoDevStopArgs,
            handler=_expo_dev_stop,
            defer_loading=True,
        ),
        ToolSpec(
            name="expo_metro_reload",
            description="Trigger Metro bundler hot reload via dev server.",
            args_model=ExpoMetroReloadArgs,
            handler=_expo_metro_reload,
            defer_loading=True,
        ),
        ToolSpec(
            name="expo_logs_capture",
            description="Read the most recent Metro log lines (.expo/metro.log).",
            args_model=ExpoLogsCaptureArgs,
            handler=_expo_logs_capture,
            defer_loading=True,
        ),
        ToolSpec(
            name="expo_eas_build",
            description="Run `eas build` (cloud or local) for ios/android/all.",
            args_model=ExpoEasBuildArgs,
            handler=_expo_eas_build,
            defer_loading=True,
        ),
        ToolSpec(
            name="expo_eas_submit",
            description="Submit a built artifact to App Store / Play via EAS.",
            args_model=ExpoEasSubmitArgs,
            handler=_expo_eas_submit,
            defer_loading=True,
        ),
        ToolSpec(
            name="expo_publish",
            description="Publish JS bundle update via `expo publish`.",
            args_model=ExpoPublishArgs,
            handler=_expo_publish,
            defer_loading=True,
        ),
        ToolSpec(
            name="expo_export",
            description="Export static bundle (`expo export`) for hosting.",
            args_model=ExpoExportArgs,
            handler=_expo_export,
            defer_loading=True,
        ),
        ToolSpec(
            name="expo_run_ios",
            description="Build + install + launch the iOS dev client.",
            args_model=ExpoRunIosArgs,
            handler=_expo_run_ios,
            defer_loading=True,
        ),
        ToolSpec(
            name="expo_run_android",
            description="Build + install + launch the Android dev client.",
            args_model=ExpoRunAndroidArgs,
            handler=_expo_run_android,
            defer_loading=True,
        ),
        ToolSpec(
            name="expo_install",
            description="Install a package via `expo install` (uses Expo-compatible versions).",
            args_model=ExpoInstallArgs,
            handler=_expo_install,
            defer_loading=True,
        ),
        ToolSpec(
            name="expo_doctor",
            description="Run `expo-doctor` to validate project deps + config.",
            args_model=ExpoDoctorArgs,
            handler=_expo_doctor,
            defer_loading=True,
        ),
    ]
