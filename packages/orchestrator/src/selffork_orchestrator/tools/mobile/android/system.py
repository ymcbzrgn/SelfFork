"""Android system tools — orientation/clipboard/property/reboot/battery + extras (8 tools)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_android_driver,
)

__all__ = [
    "AndroidGetBatteryArgs",
    "AndroidGetClipboardArgs",
    "AndroidGetOrientationArgs",
    "AndroidGetPropertyArgs",
    "AndroidRebootArgs",
    "AndroidSetClipboardArgs",
    "AndroidSetOrientationArgs",
    "AndroidSetPropertyArgs",
    "build_android_system_tools",
]


class AndroidGetOrientationArgs(ToolArgs):
    pass


class AndroidSetOrientationArgs(ToolArgs):
    orientation: Literal["PORTRAIT", "LANDSCAPE", "UPSIDE_DOWN", "LANDSCAPE_REVERSE"] = "PORTRAIT"


class AndroidGetClipboardArgs(ToolArgs):
    pass


class AndroidSetClipboardArgs(ToolArgs):
    text: str = Field(max_length=100_000)


class AndroidGetPropertyArgs(ToolArgs):
    key: str = Field(min_length=1, max_length=128)


class AndroidSetPropertyArgs(ToolArgs):
    key: str = Field(min_length=1, max_length=128)
    value: str = Field(max_length=512)


class AndroidRebootArgs(ToolArgs):
    pass


class AndroidGetBatteryArgs(ToolArgs):
    pass


async def _android_get_orientation(
    ctx: ToolContext,
    args: AndroidGetOrientationArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _get() -> dict[str, Any]:
        return {"orientation": await drv.get_orientation()}

    return await _invoke_mobile(
        ctx,
        action_type="android.get_orientation",
        target_uri=None,
        args_summary={},
        coro_factory=_get,
    )


async def _android_set_orientation(
    ctx: ToolContext,
    args: AndroidSetOrientationArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.set_orientation",
        target_uri=None,
        args_summary={"orientation": args.orientation},
        coro_factory=lambda: drv.set_orientation(args.orientation),
    )


async def _android_get_clipboard(
    ctx: ToolContext,
    args: AndroidGetClipboardArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _get() -> dict[str, Any]:
        text = await drv.get_clipboard()
        return {"text": text, "len": len(text)}

    return await _invoke_mobile(
        ctx,
        action_type="android.get_clipboard",
        target_uri=None,
        args_summary={},
        coro_factory=_get,
    )


async def _android_set_clipboard(
    ctx: ToolContext,
    args: AndroidSetClipboardArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.set_clipboard",
        target_uri=None,
        args_summary={"text_len": len(args.text)},
        coro_factory=lambda: drv.set_clipboard(args.text),
    )


async def _android_get_property(
    ctx: ToolContext,
    args: AndroidGetPropertyArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _get() -> dict[str, Any]:
        value = await drv.get_property(args.key)
        return {"key": args.key, "value": value}

    return await _invoke_mobile(
        ctx,
        action_type="android.get_property",
        target_uri=f"android-prop:{args.key}",
        args_summary={"key": args.key},
        coro_factory=_get,
    )


async def _android_set_property(
    ctx: ToolContext,
    args: AndroidSetPropertyArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.set_property",
        target_uri=f"android-prop:{args.key}",
        args_summary={"key": args.key, "value_len": len(args.value)},
        coro_factory=lambda: drv.set_property(args.key, args.value),
    )


async def _android_reboot(ctx: ToolContext, args: AndroidRebootArgs) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.reboot",
        target_uri=None,
        args_summary={},
        coro_factory=lambda: drv.reboot(),
    )


async def _android_get_battery(
    ctx: ToolContext,
    args: AndroidGetBatteryArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _get() -> dict[str, Any]:
        return {"battery": await drv.get_battery()}

    return await _invoke_mobile(
        ctx,
        action_type="android.get_battery",
        target_uri=None,
        args_summary={},
        coro_factory=_get,
    )


def build_android_system_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="android_get_orientation",
            description="Read Android device orientation.",
            args_model=AndroidGetOrientationArgs,
            handler=_android_get_orientation,
            defer_loading=False,
        ),
        ToolSpec(
            name="android_set_orientation",
            description="Set Android device orientation (auto-rotate off + user_rotation).",
            args_model=AndroidSetOrientationArgs,
            handler=_android_set_orientation,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_get_clipboard",
            description="Read text from the Android clipboard.",
            args_model=AndroidGetClipboardArgs,
            handler=_android_get_clipboard,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_set_clipboard",
            description="Write text to the Android clipboard.",
            args_model=AndroidSetClipboardArgs,
            handler=_android_set_clipboard,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_get_property",
            description="Read an Android system property (getprop).",
            args_model=AndroidGetPropertyArgs,
            handler=_android_get_property,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_set_property",
            description="Set an Android system property (setprop; root may be required).",
            args_model=AndroidSetPropertyArgs,
            handler=_android_set_property,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_reboot",
            description="Reboot the Android device (adb reboot).",
            args_model=AndroidRebootArgs,
            handler=_android_reboot,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_get_battery",
            description="Get Android battery info (dumpsys battery).",
            args_model=AndroidGetBatteryArgs,
            handler=_android_get_battery,
            defer_loading=True,
        ),
    ]
