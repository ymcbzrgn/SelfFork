"""iOS lifecycle tools — launch/terminate/activate/state/install/uninstall/background/list."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_ios_driver,
)

__all__ = [
    "IosAppActivateArgs",
    "IosAppBackgroundArgs",
    "IosAppLaunchArgs",
    "IosAppStateArgs",
    "IosAppTerminateArgs",
    "IosInstallAppArgs",
    "IosListAppsArgs",
    "IosUninstallAppArgs",
    "build_ios_lifecycle_tools",
]


class IosAppLaunchArgs(ToolArgs):
    bundle_id: str = Field(min_length=1, max_length=255)


class IosAppTerminateArgs(ToolArgs):
    bundle_id: str = Field(min_length=1, max_length=255)


class IosAppActivateArgs(ToolArgs):
    bundle_id: str = Field(min_length=1, max_length=255)


class IosAppStateArgs(ToolArgs):
    bundle_id: str = Field(min_length=1, max_length=255)


class IosInstallAppArgs(ToolArgs):
    app_path: str = Field(min_length=1, description="Path to .app bundle or .ipa")


class IosUninstallAppArgs(ToolArgs):
    bundle_id: str = Field(min_length=1, max_length=255)


class IosAppBackgroundArgs(ToolArgs):
    seconds: float = Field(default=-1, description="Background for N seconds; -1 = indefinite")


class IosListAppsArgs(ToolArgs):
    pass


async def _ios_app_launch(ctx: ToolContext, args: IosAppLaunchArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.app_launch",
        target_uri=f"ios-app:{args.bundle_id}",
        args_summary={"bundle_id": args.bundle_id},
        coro_factory=lambda: drv.app_launch(args.bundle_id),
    )


async def _ios_app_terminate(ctx: ToolContext, args: IosAppTerminateArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.app_terminate",
        target_uri=f"ios-app:{args.bundle_id}",
        args_summary={"bundle_id": args.bundle_id},
        coro_factory=lambda: drv.app_terminate(args.bundle_id),
    )


async def _ios_app_activate(ctx: ToolContext, args: IosAppActivateArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.app_activate",
        target_uri=f"ios-app:{args.bundle_id}",
        args_summary={"bundle_id": args.bundle_id},
        coro_factory=lambda: drv.app_activate(args.bundle_id),
    )


async def _ios_app_state(ctx: ToolContext, args: IosAppStateArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.app_state",
        target_uri=f"ios-app:{args.bundle_id}",
        args_summary={"bundle_id": args.bundle_id},
        coro_factory=lambda: drv.app_state(args.bundle_id),
    )


async def _ios_install_app(ctx: ToolContext, args: IosInstallAppArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.install_app",
        target_uri=f"ios-file:{args.app_path}",
        args_summary={"app_path": args.app_path},
        coro_factory=lambda: drv.install_app(args.app_path),
    )


async def _ios_uninstall_app(ctx: ToolContext, args: IosUninstallAppArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.uninstall_app",
        target_uri=f"ios-app:{args.bundle_id}",
        args_summary={"bundle_id": args.bundle_id},
        coro_factory=lambda: drv.uninstall_app(args.bundle_id),
    )


async def _ios_app_background(ctx: ToolContext, args: IosAppBackgroundArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.app_background",
        target_uri=None,
        args_summary={"seconds": args.seconds},
        coro_factory=lambda: drv.app_background(seconds=args.seconds),
    )


async def _ios_list_apps(ctx: ToolContext, args: IosListAppsArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _list() -> dict[str, Any]:
        apps = await drv.list_apps()
        return {"count": len(apps), "apps": apps[:200]}

    return await _invoke_mobile(
        ctx,
        action_type="ios.list_apps",
        target_uri=None,
        args_summary={},
        coro_factory=_list,
    )


def build_ios_lifecycle_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="ios_app_launch",
            description="Launch (or activate) an iOS app by bundle ID.",
            args_model=IosAppLaunchArgs,
            handler=_ios_app_launch,
            defer_loading=False,
        ),
        ToolSpec(
            name="ios_app_terminate",
            description="Terminate a running iOS app by bundle ID.",
            args_model=IosAppTerminateArgs,
            handler=_ios_app_terminate,
            defer_loading=False,
        ),
        ToolSpec(
            name="ios_list_apps",
            description="List installed iOS apps with bundle IDs.",
            args_model=IosListAppsArgs,
            handler=_ios_list_apps,
            defer_loading=False,
        ),
        ToolSpec(
            name="ios_app_activate",
            description="Bring an iOS app to the foreground (alias of launch).",
            args_model=IosAppActivateArgs,
            handler=_ios_app_activate,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_app_state",
            description=(
                "Query iOS app state (0=not installed, 1=not running, "
                "2=suspended, 3=background, 4=foreground)."
            ),
            args_model=IosAppStateArgs,
            handler=_ios_app_state,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_install_app",
            description="Install an iOS .app/.ipa bundle (path on host).",
            args_model=IosInstallAppArgs,
            handler=_ios_install_app,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_uninstall_app",
            description="Uninstall an iOS app by bundle ID.",
            args_model=IosUninstallAppArgs,
            handler=_ios_uninstall_app,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_app_background",
            description="Send the current iOS app to background for N seconds.",
            args_model=IosAppBackgroundArgs,
            handler=_ios_app_background,
            defer_loading=True,
        ),
    ]
