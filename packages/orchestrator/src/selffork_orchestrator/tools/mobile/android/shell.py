"""Android shell + file + log tools — pull/push/logcat/dumpsys/screenrecord/install_xapk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_android_driver,
)

__all__ = [
    "AndroidDumpsysArgs",
    "AndroidInstallXapkArgs",
    "AndroidLogcatArgs",
    "AndroidPullArgs",
    "AndroidPushArgs",
    "AndroidScreenrecordStartArgs",
    "AndroidScreenrecordStopArgs",
    "AndroidShellArgs",
    "build_android_shell_tools",
]


class AndroidShellArgs(ToolArgs):
    command: str = Field(min_length=1, max_length=8_192)


class AndroidPullArgs(ToolArgs):
    remote: str = Field(min_length=1, max_length=4_096)
    local: str = Field(min_length=1, max_length=4_096)


class AndroidPushArgs(ToolArgs):
    local: str = Field(min_length=1, max_length=4_096)
    remote: str = Field(min_length=1, max_length=4_096)


class AndroidLogcatArgs(ToolArgs):
    tag_filter: str | None = Field(default=None, max_length=512)
    max_lines: int = Field(default=200, ge=1, le=10_000)
    clear: bool = False


class AndroidDumpsysArgs(ToolArgs):
    service: str = Field(min_length=1, max_length=128)


class AndroidScreenrecordStartArgs(ToolArgs):
    output_path: str = Field(min_length=1, max_length=4_096)


class AndroidScreenrecordStopArgs(ToolArgs):
    pass


class AndroidInstallXapkArgs(ToolArgs):
    xapk_dir: str = Field(min_length=1, description="Directory containing split APKs")


async def _android_shell(ctx: ToolContext, args: AndroidShellArgs) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _run() -> dict[str, Any]:
        out = await drv.shell(args.command)
        return {"output": out[:16384]}

    return await _invoke_mobile(
        ctx,
        action_type="android.shell",
        target_uri=None,
        args_summary={"cmd_len": len(args.command)},
        coro_factory=_run,
    )


async def _android_pull(ctx: ToolContext, args: AndroidPullArgs) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.pull",
        target_uri=f"android-file:{args.remote}",
        args_summary={"remote": args.remote, "local": args.local},
        coro_factory=lambda: drv.pull(args.remote, Path(args.local)),
    )


async def _android_push(ctx: ToolContext, args: AndroidPushArgs) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.push",
        target_uri=f"android-file:{args.remote}",
        args_summary={"local": args.local, "remote": args.remote},
        coro_factory=lambda: drv.push(Path(args.local), args.remote),
    )


async def _android_logcat(ctx: ToolContext, args: AndroidLogcatArgs) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _grab() -> dict[str, Any]:
        text = await drv.logcat(
            tag_filter=args.tag_filter,
            max_lines=args.max_lines,
            clear=args.clear,
        )
        return {"text_len": len(text), "preview": text[:8192]}

    return await _invoke_mobile(
        ctx,
        action_type="android.logcat",
        target_uri=None,
        args_summary={
            "tag_filter": args.tag_filter,
            "max_lines": args.max_lines,
            "clear": args.clear,
        },
        coro_factory=_grab,
    )


async def _android_dumpsys(
    ctx: ToolContext,
    args: AndroidDumpsysArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _dump() -> dict[str, Any]:
        text = await drv.dumpsys(args.service)
        return {"text_len": len(text), "preview": text[:8192]}

    return await _invoke_mobile(
        ctx,
        action_type="android.dumpsys",
        target_uri=f"android-svc:{args.service}",
        args_summary={"service": args.service},
        coro_factory=_dump,
    )


async def _android_screenrecord_start(
    ctx: ToolContext,
    args: AndroidScreenrecordStartArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.screenrecord_start",
        target_uri=f"android-file:{args.output_path}",
        args_summary={"output_path": args.output_path},
        coro_factory=lambda: drv.screenrecord_start(Path(args.output_path)),
    )


async def _android_screenrecord_stop(
    ctx: ToolContext,
    args: AndroidScreenrecordStopArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _stop() -> dict[str, Any]:
        path = await drv.screenrecord_stop()
        return {"output_path": str(path) if path else None}

    return await _invoke_mobile(
        ctx,
        action_type="android.screenrecord_stop",
        target_uri=None,
        args_summary={},
        coro_factory=_stop,
    )


async def _android_install_xapk(
    ctx: ToolContext,
    args: AndroidInstallXapkArgs,
) -> dict[str, Any]:
    """Install a split-APK bundle (XAPK directory)."""
    drv = _require_android_driver(ctx)

    async def _install() -> dict[str, Any]:
        xapk_dir = Path(args.xapk_dir)
        apks = sorted(xapk_dir.glob("*.apk"))  # noqa: ASYNC240 — sync glob is fast
        if not apks:
            return {"installed": 0, "error": "no .apk files found"}
        out = await drv.install_multiple_apks(apks)
        return {"installed": len(apks), "output": out[:1024]}

    return await _invoke_mobile(
        ctx,
        action_type="android.install_xapk",
        target_uri=f"android-file:{args.xapk_dir}",
        args_summary={"xapk_dir": args.xapk_dir},
        coro_factory=_install,
    )


def build_android_shell_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="android_shell",
            description="Run an arbitrary adb shell command and capture output.",
            args_model=AndroidShellArgs,
            handler=_android_shell,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_pull",
            description="Pull a file from the Android device to the host.",
            args_model=AndroidPullArgs,
            handler=_android_pull,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_push",
            description="Push a file from the host to the Android device.",
            args_model=AndroidPushArgs,
            handler=_android_push,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_logcat",
            description=(
                "Read recent logcat output with optional tag filter; set clear=true to flush first."
            ),
            args_model=AndroidLogcatArgs,
            handler=_android_logcat,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_dumpsys",
            description="Dump the state of a system service (dumpsys <service>).",
            args_model=AndroidDumpsysArgs,
            handler=_android_dumpsys,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_screenrecord_start",
            description="Start screenrecord to /sdcard then pull on stop.",
            args_model=AndroidScreenrecordStartArgs,
            handler=_android_screenrecord_start,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_screenrecord_stop",
            description="Stop active Android screenrecord; returns local path.",
            args_model=AndroidScreenrecordStopArgs,
            handler=_android_screenrecord_stop,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_install_xapk",
            description="Install a split-APK bundle (XAPK) via install-multiple.",
            args_model=AndroidInstallXapkArgs,
            handler=_android_install_xapk,
            defer_loading=True,
        ),
    ]
