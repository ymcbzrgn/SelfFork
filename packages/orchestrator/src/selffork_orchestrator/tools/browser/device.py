"""Browser device emulation tools — emulate_device/geo/locale/timezone/color_scheme (5)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.browser._internal import (
    _invoke_browser,
    _require_browser_driver,
)

__all__ = [
    "BrowserEmulateDeviceArgs",
    "BrowserSetColorSchemeArgs",
    "BrowserSetGeolocationArgs",
    "BrowserSetLocaleArgs",
    "BrowserSetTimezoneArgs",
    "build_browser_device_tools",
]


class BrowserEmulateDeviceArgs(ToolArgs):
    device_name: str = Field(
        min_length=1, max_length=128, description="e.g. 'iPhone 13', 'Pixel 7'"
    )  # noqa: E501


class BrowserSetGeolocationArgs(ToolArgs):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    accuracy: float = Field(default=1.0, ge=0.0, le=10_000.0)


class BrowserSetLocaleArgs(ToolArgs):
    locale: str = Field(min_length=2, max_length=16, description="e.g. 'en-US', 'tr-TR'")


class BrowserSetTimezoneArgs(ToolArgs):
    timezone_id: str = Field(
        min_length=1, max_length=64, description="e.g. 'America/New_York', 'Europe/Istanbul'"
    )  # noqa: E501


class BrowserSetColorSchemeArgs(ToolArgs):
    scheme: Literal["light", "dark", "no-preference"] = "light"


async def _browser_emulate_device(
    ctx: ToolContext,
    args: BrowserEmulateDeviceArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.emulate_device",
        target_uri=None,
        args_summary={"device_name": args.device_name},
        coro_factory=lambda: drv.emulate_device(args.device_name),
    )


async def _browser_set_geolocation(
    ctx: ToolContext,
    args: BrowserSetGeolocationArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.set_geolocation",
        target_uri=None,
        args_summary={
            "latitude": args.latitude,
            "longitude": args.longitude,
            "accuracy": args.accuracy,
        },  # noqa: E501
        coro_factory=lambda: drv.set_geolocation(args.latitude, args.longitude, args.accuracy),
    )


async def _browser_set_locale(
    ctx: ToolContext,
    args: BrowserSetLocaleArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.set_locale",
        target_uri=None,
        args_summary={"locale": args.locale},
        coro_factory=lambda: drv.set_locale(args.locale),
    )


async def _browser_set_timezone(
    ctx: ToolContext,
    args: BrowserSetTimezoneArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.set_timezone",
        target_uri=None,
        args_summary={"timezone_id": args.timezone_id},
        coro_factory=lambda: drv.set_timezone(args.timezone_id),
    )


async def _browser_set_color_scheme(
    ctx: ToolContext,
    args: BrowserSetColorSchemeArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.set_color_scheme",
        target_uri=None,
        args_summary={"scheme": args.scheme},
        coro_factory=lambda: drv.set_color_scheme(args.scheme),
    )


def build_browser_device_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="browser_emulate_device",
            description="Emulate a device profile (iPhone, Pixel, etc.) for the next start cycle.",  # noqa: E501
            args_model=BrowserEmulateDeviceArgs,
            handler=_browser_emulate_device,
            defer_loading=True,
        ),  # noqa: E501
        ToolSpec(
            name="browser_set_geolocation",
            description="Set the browser's reported GPS location (lat/lon/accuracy).",
            args_model=BrowserSetGeolocationArgs,
            handler=_browser_set_geolocation,
            defer_loading=True,
        ),  # noqa: E501
        ToolSpec(
            name="browser_set_locale",
            description="Set the browser locale for the next start cycle.",
            args_model=BrowserSetLocaleArgs,
            handler=_browser_set_locale,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_set_timezone",
            description="Override the browser timezone via CDP (Chromium).",
            args_model=BrowserSetTimezoneArgs,
            handler=_browser_set_timezone,
            defer_loading=True,
        ),  # noqa: E501
        ToolSpec(
            name="browser_set_color_scheme",
            description="Emulate prefers-color-scheme (light/dark/no-preference).",
            args_model=BrowserSetColorSchemeArgs,
            handler=_browser_set_color_scheme,
            defer_loading=True,
        ),  # noqa: E501
    ]
