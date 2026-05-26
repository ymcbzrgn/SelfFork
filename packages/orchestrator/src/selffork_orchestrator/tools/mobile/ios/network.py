"""iOS network/media tools — open_url/geolocation/record_video (5 tools)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_ios_driver,
)

__all__ = [
    "IosGetGeolocationArgs",
    "IosOpenUrlArgs",
    "IosRecordVideoStartArgs",
    "IosRecordVideoStopArgs",
    "IosSetGeolocationArgs",
    "build_ios_network_tools",
]


class IosOpenUrlArgs(ToolArgs):
    url: str = Field(min_length=1, max_length=8_192)


class IosSetGeolocationArgs(ToolArgs):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    altitude: float = Field(default=0.0, ge=-1_000.0, le=20_000.0)


class IosGetGeolocationArgs(ToolArgs):
    pass


class IosRecordVideoStartArgs(ToolArgs):
    output_path: str = Field(min_length=1)


class IosRecordVideoStopArgs(ToolArgs):
    pass


async def _ios_open_url(ctx: ToolContext, args: IosOpenUrlArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.open_url",
        target_uri=args.url,
        args_summary={"url": args.url},
        coro_factory=lambda: drv.open_url(args.url),
    )


async def _ios_set_geolocation(
    ctx: ToolContext, args: IosSetGeolocationArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.set_geolocation",
        target_uri=None,
        args_summary={
            "latitude": args.latitude,
            "longitude": args.longitude,
            "altitude": args.altitude,
        },
        coro_factory=lambda: drv.set_geolocation(
            args.latitude, args.longitude, altitude=args.altitude,
        ),
    )


async def _ios_get_geolocation(
    ctx: ToolContext, args: IosGetGeolocationArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _get() -> dict[str, Any]:
        return await drv.get_geolocation()  # type: ignore[no-any-return]

    return await _invoke_mobile(
        ctx,
        action_type="ios.get_geolocation",
        target_uri=None,
        args_summary={},
        coro_factory=_get,
    )


async def _ios_record_video_start(
    ctx: ToolContext, args: IosRecordVideoStartArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.record_video_start",
        target_uri=f"ios-file:{args.output_path}",
        args_summary={"output_path": args.output_path},
        coro_factory=lambda: drv.record_video_start(Path(args.output_path)),
    )


async def _ios_record_video_stop(
    ctx: ToolContext, args: IosRecordVideoStopArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _stop() -> dict[str, Any]:
        path = await drv.record_video_stop()
        return {"output_path": str(path) if path else None}

    return await _invoke_mobile(
        ctx,
        action_type="ios.record_video_stop",
        target_uri=None,
        args_summary={},
        coro_factory=_stop,
    )


def build_ios_network_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="ios_open_url",
            description=(
                "Open a URL on iOS (deep link or universal link). Uses "
                "Appium deepLink first, simctl openurl as fallback."
            ),
            args_model=IosOpenUrlArgs,
            handler=_ios_open_url,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_set_geolocation",
            description="Set the iOS simulator GPS location (lat/lon/alt).",
            args_model=IosSetGeolocationArgs,
            handler=_ios_set_geolocation,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_get_geolocation",
            description="Read the iOS simulator GPS location.",
            args_model=IosGetGeolocationArgs,
            handler=_ios_get_geolocation,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_record_video_start",
            description="Start recording iOS simulator screen to an MP4 file.",
            args_model=IosRecordVideoStartArgs,
            handler=_ios_record_video_start,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_record_video_stop",
            description="Stop the active iOS screen recording; returns path.",
            args_model=IosRecordVideoStopArgs,
            handler=_ios_record_video_stop,
            defer_loading=True,
        ),
    ]
