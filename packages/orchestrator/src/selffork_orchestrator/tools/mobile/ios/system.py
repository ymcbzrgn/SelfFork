"""iOS system tools — orientation/clipboard/lock/unlock/keyboard/press_button (8 tools)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_ios_driver,
)

__all__ = [
    "IosGetClipboardArgs",
    "IosGetOrientationArgs",
    "IosLockDeviceArgs",
    "IosPressButtonArgs",
    "IosSetClipboardArgs",
    "IosSetOrientationArgs",
    "IosTerminateKeyboardArgs",
    "IosUnlockDeviceArgs",
    "build_ios_system_tools",
]


class IosGetOrientationArgs(ToolArgs):
    pass


class IosSetOrientationArgs(ToolArgs):
    orientation: Literal["PORTRAIT", "LANDSCAPE"] = "PORTRAIT"


class IosGetClipboardArgs(ToolArgs):
    pass


class IosSetClipboardArgs(ToolArgs):
    text: str = Field(max_length=100_000)


class IosTerminateKeyboardArgs(ToolArgs):
    pass


class IosLockDeviceArgs(ToolArgs):
    pass


class IosUnlockDeviceArgs(ToolArgs):
    pass


class IosPressButtonArgs(ToolArgs):
    button: Literal[
        "home", "lock", "volumeup", "volumedown", "siri",
    ] = Field(description="Hardware button to press")


async def _ios_get_orientation(ctx: ToolContext, args: IosGetOrientationArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _get() -> dict[str, Any]:
        return {"orientation": await drv.get_orientation()}

    return await _invoke_mobile(
        ctx,
        action_type="ios.get_orientation",
        target_uri=None,
        args_summary={},
        coro_factory=_get,
    )


async def _ios_set_orientation(ctx: ToolContext, args: IosSetOrientationArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.set_orientation",
        target_uri=None,
        args_summary={"orientation": args.orientation},
        coro_factory=lambda: drv.set_orientation(args.orientation),
    )


async def _ios_get_clipboard(ctx: ToolContext, args: IosGetClipboardArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _get() -> dict[str, Any]:
        text = await drv.get_clipboard()
        return {"text": text, "len": len(text)}

    return await _invoke_mobile(
        ctx,
        action_type="ios.get_clipboard",
        target_uri=None,
        args_summary={},
        coro_factory=_get,
    )


async def _ios_set_clipboard(ctx: ToolContext, args: IosSetClipboardArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.set_clipboard",
        target_uri=None,
        args_summary={"text_len": len(args.text)},
        coro_factory=lambda: drv.set_clipboard(args.text),
    )


async def _ios_terminate_keyboard(
    ctx: ToolContext, args: IosTerminateKeyboardArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.terminate_keyboard",
        target_uri=None,
        args_summary={},
        coro_factory=lambda: drv.terminate_keyboard(),
    )


async def _ios_lock_device(ctx: ToolContext, args: IosLockDeviceArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.lock_device",
        target_uri=None,
        args_summary={},
        coro_factory=lambda: drv.press_button("lock"),
    )


async def _ios_unlock_device(ctx: ToolContext, args: IosUnlockDeviceArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    # Press lock twice = wake the screen; user must then swipe to unlock on
    # production-style locks. Simulator passcode is off by default.
    return await _invoke_mobile(
        ctx,
        action_type="ios.unlock_device",
        target_uri=None,
        args_summary={},
        coro_factory=lambda: drv.press_button("lock"),
    )


async def _ios_press_button(ctx: ToolContext, args: IosPressButtonArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.press_button",
        target_uri=None,
        args_summary={"button": args.button},
        coro_factory=lambda: drv.press_button(args.button),
    )


def build_ios_system_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="ios_get_orientation",
            description="Read iOS device orientation (PORTRAIT / LANDSCAPE).",
            args_model=IosGetOrientationArgs,
            handler=_ios_get_orientation,
            defer_loading=False,
        ),
        ToolSpec(
            name="ios_set_orientation",
            description="Set iOS device orientation.",
            args_model=IosSetOrientationArgs,
            handler=_ios_set_orientation,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_get_clipboard",
            description="Read text from the iOS clipboard.",
            args_model=IosGetClipboardArgs,
            handler=_ios_get_clipboard,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_set_clipboard",
            description="Write text to the iOS clipboard.",
            args_model=IosSetClipboardArgs,
            handler=_ios_set_clipboard,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_terminate_keyboard",
            description="Hide the iOS software keyboard.",
            args_model=IosTerminateKeyboardArgs,
            handler=_ios_terminate_keyboard,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_lock_device",
            description="Lock the iOS device (press lock button).",
            args_model=IosLockDeviceArgs,
            handler=_ios_lock_device,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_unlock_device",
            description="Wake the iOS device (press lock; user must swipe).",
            args_model=IosUnlockDeviceArgs,
            handler=_ios_unlock_device,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_press_button",
            description="Press an iOS hardware button (home/lock/volume/siri).",
            args_model=IosPressButtonArgs,
            handler=_ios_press_button,
            defer_loading=True,
        ),
    ]
