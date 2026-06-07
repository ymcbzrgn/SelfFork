"""Android emulator + device-level tools — list / set_geolocation / emulator_boot/shutdown (4)."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_android_driver,
)

__all__ = [
    "AndroidDeviceListArgs",
    "AndroidEmulatorBootArgs",
    "AndroidEmulatorShutdownArgs",
    "AndroidSetGeolocationArgs",
    "build_android_emulator_tools",
]


class AndroidDeviceListArgs(ToolArgs):
    pass


class AndroidSetGeolocationArgs(ToolArgs):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class AndroidEmulatorBootArgs(ToolArgs):
    avd: str = Field(min_length=1, max_length=128, description="AVD name")


class AndroidEmulatorShutdownArgs(ToolArgs):
    serial: str = Field(min_length=1, max_length=64)


async def _android_device_list(
    ctx: ToolContext,
    args: AndroidDeviceListArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _list() -> dict[str, Any]:
        devices = await drv.device_list()
        return {"count": len(devices), "devices": devices[:100]}

    return await _invoke_mobile(
        ctx,
        action_type="android.device_list",
        target_uri=None,
        args_summary={},
        coro_factory=_list,
    )


async def _android_set_geolocation(
    ctx: ToolContext,
    args: AndroidSetGeolocationArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _set() -> dict[str, Any]:
        text = await drv.set_geolocation(args.latitude, args.longitude)
        return {"output": text[:256]}

    return await _invoke_mobile(
        ctx,
        action_type="android.set_geolocation",
        target_uri=None,
        args_summary={
            "latitude": args.latitude,
            "longitude": args.longitude,
        },
        coro_factory=_set,
    )


async def _android_emulator_boot(
    ctx: ToolContext,
    args: AndroidEmulatorBootArgs,
) -> dict[str, Any]:
    _require_android_driver(ctx)

    async def _boot() -> dict[str, Any]:
        # ``emulator -avd <name>`` blocks; spawn detached, return PID.
        proc = await asyncio.create_subprocess_exec(
            "emulator",
            "-avd",
            args.avd,
            "-no-snapshot-load",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"pid": proc.pid, "avd": args.avd}

    return await _invoke_mobile(
        ctx,
        action_type="android.emulator_boot",
        target_uri=f"android-avd:{args.avd}",
        args_summary={"avd": args.avd},
        coro_factory=_boot,
    )


async def _android_emulator_shutdown(
    ctx: ToolContext,
    args: AndroidEmulatorShutdownArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _shutdown() -> dict[str, Any]:
        # Route the kill through the driver's underlying ADB helper.
        try:
            await drv.fallback._adb("-s", args.serial, "emu", "kill")
        except Exception as exc:  # kill is best-effort
            return {"killed": None, "error": str(exc)}
        return {"killed": args.serial}

    return await _invoke_mobile(
        ctx,
        action_type="android.emulator_shutdown",
        target_uri=f"android-serial:{args.serial}",
        args_summary={"serial": args.serial},
        coro_factory=_shutdown,
    )


def build_android_emulator_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="android_device_list",
            description="List attached Android devices/emulators (adb devices -l).",
            args_model=AndroidDeviceListArgs,
            handler=_android_device_list,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_set_geolocation",
            description="Set Android emulator GPS via emu geo fix.",
            args_model=AndroidSetGeolocationArgs,
            handler=_android_set_geolocation,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_emulator_boot",
            description="Boot a named AVD (Android Virtual Device) detached.",
            args_model=AndroidEmulatorBootArgs,
            handler=_android_emulator_boot,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_emulator_shutdown",
            description="Kill a running emulator by serial (adb emu kill).",
            args_model=AndroidEmulatorShutdownArgs,
            handler=_android_emulator_shutdown,
            defer_loading=True,
        ),
    ]
