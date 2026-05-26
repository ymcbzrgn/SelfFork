"""iOS simulator tools — list/boot/shutdown/erase/biometric/logs/push/status_bar/appearance (10)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_ios_driver,
)

__all__ = [
    "IosBiometricMatchArgs",
    "IosBiometricNoMatchArgs",
    "IosGetLogsArgs",
    "IosSendPushNotificationArgs",
    "IosSetAppearanceArgs",
    "IosSimulatorBootArgs",
    "IosSimulatorEraseArgs",
    "IosSimulatorListArgs",
    "IosSimulatorShutdownArgs",
    "IosStatusBarOverrideArgs",
    "build_ios_simulator_tools",
]


class IosSimulatorListArgs(ToolArgs):
    pass


class IosSimulatorBootArgs(ToolArgs):
    udid: str = Field(min_length=10)


class IosSimulatorShutdownArgs(ToolArgs):
    udid: str = Field(min_length=10)


class IosSimulatorEraseArgs(ToolArgs):
    udid: str = Field(min_length=10)


class IosBiometricMatchArgs(ToolArgs):
    pass


class IosBiometricNoMatchArgs(ToolArgs):
    pass


class IosGetLogsArgs(ToolArgs):
    predicate: str | None = Field(default=None, max_length=2048)
    last: str | None = Field(default="1m", description="e.g. '5m', '1h'")


class IosSendPushNotificationArgs(ToolArgs):
    payload_path: str = Field(min_length=1, description="JSON payload path")
    bundle_id: str = Field(min_length=1, max_length=255)


class IosStatusBarOverrideArgs(ToolArgs):
    time: str | None = None
    battery_state: Literal["charging", "charged", "discharging"] | None = None
    cellular_bars: int | None = Field(default=None, ge=0, le=4)
    wifi_bars: int | None = Field(default=None, ge=0, le=3)


class IosSetAppearanceArgs(ToolArgs):
    appearance: Literal["light", "dark"] = "light"


async def _ios_simulator_list(ctx: ToolContext, args: IosSimulatorListArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _list() -> dict[str, Any]:
        devices = await drv.simulator_list()
        return {"count": len(devices), "devices": devices[:200]}

    return await _invoke_mobile(
        ctx,
        action_type="ios.simulator_list",
        target_uri=None,
        args_summary={},
        coro_factory=_list,
    )


async def _ios_simulator_boot(ctx: ToolContext, args: IosSimulatorBootArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _boot() -> dict[str, Any]:
        return {"udid": await drv.simulator_boot(args.udid)}

    return await _invoke_mobile(
        ctx,
        action_type="ios.simulator_boot",
        target_uri=f"ios-sim:{args.udid}",
        args_summary={"udid": args.udid},
        coro_factory=_boot,
    )


async def _ios_simulator_shutdown(
    ctx: ToolContext, args: IosSimulatorShutdownArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.simulator_shutdown",
        target_uri=f"ios-sim:{args.udid}",
        args_summary={"udid": args.udid},
        coro_factory=lambda: drv.simulator_shutdown(args.udid),
    )


async def _ios_simulator_erase(
    ctx: ToolContext, args: IosSimulatorEraseArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.simulator_erase",
        target_uri=f"ios-sim:{args.udid}",
        args_summary={"udid": args.udid},
        coro_factory=lambda: drv.simulator_erase(args.udid),
    )


async def _ios_biometric_match(
    ctx: ToolContext, args: IosBiometricMatchArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.biometric_match",
        target_uri=None,
        args_summary={},
        coro_factory=lambda: drv.biometric_match(),
    )


async def _ios_biometric_no_match(
    ctx: ToolContext, args: IosBiometricNoMatchArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.biometric_no_match",
        target_uri=None,
        args_summary={},
        coro_factory=lambda: drv.biometric_no_match(),
    )


async def _ios_get_logs(ctx: ToolContext, args: IosGetLogsArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _get() -> dict[str, Any]:
        text = await drv.get_logs(predicate=args.predicate, last=args.last)
        return {"text_len": len(text), "preview": text[:8192]}

    return await _invoke_mobile(
        ctx,
        action_type="ios.get_logs",
        target_uri=None,
        args_summary={"predicate": args.predicate, "last": args.last},
        coro_factory=_get,
    )


async def _ios_send_push_notification(
    ctx: ToolContext, args: IosSendPushNotificationArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.send_push_notification",
        target_uri=f"ios-app:{args.bundle_id}",
        args_summary={
            "bundle_id": args.bundle_id,
            "payload_path": args.payload_path,
        },
        coro_factory=lambda: drv.send_push_notification(
            Path(args.payload_path), args.bundle_id,
        ),
    )


async def _ios_status_bar_override(
    ctx: ToolContext, args: IosStatusBarOverrideArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.status_bar_override",
        target_uri=None,
        args_summary=args.model_dump(),
        coro_factory=lambda: drv.status_bar_override(
            time=args.time,
            battery_state=args.battery_state,
            cellular_bars=args.cellular_bars,
            wifi_bars=args.wifi_bars,
        ),
    )


async def _ios_set_appearance(
    ctx: ToolContext, args: IosSetAppearanceArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.set_appearance",
        target_uri=None,
        args_summary={"appearance": args.appearance},
        coro_factory=lambda: drv.set_appearance(args.appearance),
    )


def build_ios_simulator_tools() -> list[ToolSpec[Any]]:
    # All simulator tools are deferred — operator-level operations, not
    # part of the agentic mobile observe→act loop.
    return [
        ToolSpec(
            name="ios_simulator_list",
            description="List all iOS simulators (name/udid/state/runtime).",
            args_model=IosSimulatorListArgs,
            handler=_ios_simulator_list,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_simulator_boot",
            description="Boot a specific iOS simulator by UDID.",
            args_model=IosSimulatorBootArgs,
            handler=_ios_simulator_boot,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_simulator_shutdown",
            description="Shut down a specific iOS simulator by UDID.",
            args_model=IosSimulatorShutdownArgs,
            handler=_ios_simulator_shutdown,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_simulator_erase",
            description="Erase a specific iOS simulator (factory reset).",
            args_model=IosSimulatorEraseArgs,
            handler=_ios_simulator_erase,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_biometric_match",
            description="Simulate a successful Face/Touch ID match.",
            args_model=IosBiometricMatchArgs,
            handler=_ios_biometric_match,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_biometric_no_match",
            description="Simulate a failed Face/Touch ID attempt.",
            args_model=IosBiometricNoMatchArgs,
            handler=_ios_biometric_no_match,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_get_logs",
            description="Read iOS unified logs (filterable by predicate + window).",
            args_model=IosGetLogsArgs,
            handler=_ios_get_logs,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_send_push_notification",
            description="Deliver an APNs payload to an installed app (simctl push).",
            args_model=IosSendPushNotificationArgs,
            handler=_ios_send_push_notification,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_status_bar_override",
            description=(
                "Override status bar (time, battery state, cellular/wifi "
                "bars) for screenshot consistency."
            ),
            args_model=IosStatusBarOverrideArgs,
            handler=_ios_status_bar_override,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_set_appearance",
            description="Set iOS UI appearance (light/dark).",
            args_model=IosSetAppearanceArgs,
            handler=_ios_set_appearance,
            defer_loading=True,
        ),
    ]
