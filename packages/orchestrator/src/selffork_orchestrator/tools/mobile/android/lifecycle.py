"""Android lifecycle tools — launch/terminate/force_stop/clear_data/install/uninstall/list/activate."""  # noqa: E501

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
    "AndroidAppActivateArgs",
    "AndroidAppClearDataArgs",
    "AndroidAppForceStopArgs",
    "AndroidAppLaunchArgs",
    "AndroidAppTerminateArgs",
    "AndroidInstallAppArgs",
    "AndroidListAppsArgs",
    "AndroidUninstallAppArgs",
    "build_android_lifecycle_tools",
]


class AndroidAppLaunchArgs(ToolArgs):
    package: str = Field(min_length=1, max_length=255)


class AndroidAppTerminateArgs(ToolArgs):
    package: str = Field(min_length=1, max_length=255)


class AndroidAppForceStopArgs(ToolArgs):
    package: str = Field(min_length=1, max_length=255)


class AndroidAppClearDataArgs(ToolArgs):
    package: str = Field(min_length=1, max_length=255)


class AndroidInstallAppArgs(ToolArgs):
    apk_path: str = Field(min_length=1)


class AndroidUninstallAppArgs(ToolArgs):
    package: str = Field(min_length=1, max_length=255)


class AndroidListAppsArgs(ToolArgs):
    pass


class AndroidAppActivateArgs(ToolArgs):
    package: str = Field(min_length=1, max_length=255)


async def _android_app_launch(
    ctx: ToolContext,
    args: AndroidAppLaunchArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.app_launch",
        target_uri=f"android-app:{args.package}",
        args_summary={"package": args.package},
        coro_factory=lambda: drv.app_launch(args.package),
    )


async def _android_app_terminate(
    ctx: ToolContext,
    args: AndroidAppTerminateArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.app_terminate",
        target_uri=f"android-app:{args.package}",
        args_summary={"package": args.package},
        coro_factory=lambda: drv.app_terminate(args.package),
    )


async def _android_app_force_stop(
    ctx: ToolContext,
    args: AndroidAppForceStopArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.app_force_stop",
        target_uri=f"android-app:{args.package}",
        args_summary={"package": args.package},
        coro_factory=lambda: drv.app_force_stop(args.package),
    )


async def _android_app_clear_data(
    ctx: ToolContext,
    args: AndroidAppClearDataArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.app_clear_data",
        target_uri=f"android-app:{args.package}",
        args_summary={"package": args.package},
        coro_factory=lambda: drv.app_clear_data(args.package),
    )


async def _android_install_app(
    ctx: ToolContext,
    args: AndroidInstallAppArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.install_app",
        target_uri=f"android-file:{args.apk_path}",
        args_summary={"apk_path": args.apk_path},
        coro_factory=lambda: drv.install_app(Path(args.apk_path)),
    )


async def _android_uninstall_app(
    ctx: ToolContext,
    args: AndroidUninstallAppArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.uninstall_app",
        target_uri=f"android-app:{args.package}",
        args_summary={"package": args.package},
        coro_factory=lambda: drv.uninstall_app(args.package),
    )


async def _android_list_apps(
    ctx: ToolContext,
    args: AndroidListAppsArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _list() -> dict[str, Any]:
        apps = await drv.list_apps()
        return {"count": len(apps), "apps": apps[:500]}

    return await _invoke_mobile(
        ctx,
        action_type="android.list_apps",
        target_uri=None,
        args_summary={},
        coro_factory=_list,
    )


async def _android_app_activate(
    ctx: ToolContext,
    args: AndroidAppActivateArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.app_activate",
        target_uri=f"android-app:{args.package}",
        args_summary={"package": args.package},
        coro_factory=lambda: drv.app_activate(args.package),
    )


def build_android_lifecycle_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="android_app_launch",
            description="Launch an Android app by package name.",
            args_model=AndroidAppLaunchArgs,
            handler=_android_app_launch,
            defer_loading=False,
        ),
        ToolSpec(
            name="android_app_terminate",
            description="Terminate an Android app gracefully (mobile-mcp).",
            args_model=AndroidAppTerminateArgs,
            handler=_android_app_terminate,
            defer_loading=False,
        ),
        ToolSpec(
            name="android_list_apps",
            description="List installed Android packages (mobile-mcp + pm fallback).",
            args_model=AndroidListAppsArgs,
            handler=_android_list_apps,
            defer_loading=False,
        ),
        ToolSpec(
            name="android_app_force_stop",
            description="Force-stop an Android app (am force-stop).",
            args_model=AndroidAppForceStopArgs,
            handler=_android_app_force_stop,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_app_clear_data",
            description="Clear app data + cache (pm clear).",
            args_model=AndroidAppClearDataArgs,
            handler=_android_app_clear_data,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_install_app",
            description="Install an APK from a host path (adb install -r).",
            args_model=AndroidInstallAppArgs,
            handler=_android_install_app,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_uninstall_app",
            description="Uninstall an Android app by package (adb uninstall).",
            args_model=AndroidUninstallAppArgs,
            handler=_android_uninstall_app,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_app_activate",
            description="Bring an Android app to the foreground (alias of launch).",
            args_model=AndroidAppActivateArgs,
            handler=_android_app_activate,
            defer_loading=True,
        ),
    ]
