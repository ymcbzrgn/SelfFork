"""Android interaction tools — tap/type/swipe/scroll/gesture/key (9 tools)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_android_driver,
)

__all__ = [
    "AndroidClearTextArgs",
    "AndroidClickArgs",
    "AndroidDoubleClickArgs",
    "AndroidLongPressArgs",
    "AndroidPinchArgs",
    "AndroidPressKeyArgs",
    "AndroidScrollArgs",
    "AndroidSwipeArgs",
    "AndroidTypeArgs",
    "build_android_interaction_tools",
]


class AndroidClickArgs(ToolArgs):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class AndroidDoubleClickArgs(ToolArgs):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class AndroidLongPressArgs(ToolArgs):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    duration_ms: int = Field(default=800, ge=100, le=10_000)


class AndroidTypeArgs(ToolArgs):
    text: str = Field(min_length=1, max_length=10_000)
    clear_first: bool = False


class AndroidClearTextArgs(ToolArgs):
    pass


class AndroidSwipeArgs(ToolArgs):
    start_x: int = Field(ge=0)
    start_y: int = Field(ge=0)
    end_x: int = Field(ge=0)
    end_y: int = Field(ge=0)
    duration_ms: int = Field(default=250, ge=50, le=5_000)


class AndroidScrollArgs(ToolArgs):
    direction: Literal["up", "down", "left", "right"] = "down"
    amount: int = Field(default=300, ge=10, le=10_000)


class AndroidPressKeyArgs(ToolArgs):
    key: Literal[
        "back",
        "home",
        "menu",
        "app_switch",
        "power",
        "volume_up",
        "volume_down",
    ] = Field(description="Android hardware/system key")


class AndroidPinchArgs(ToolArgs):
    scale: float = Field(ge=0.1, le=10.0)
    velocity: float = Field(default=1.0, ge=0.1, le=10.0)


# Per AndroidDriver.click contract: requires bbox to compute center.
# Our tool takes raw (x, y) and dispatches via mcp.tap directly.


async def _android_click(ctx: ToolContext, args: AndroidClickArgs) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.click",
        target_uri=f"android:tap@{args.x},{args.y}",
        args_summary={"x": args.x, "y": args.y},
        coro_factory=lambda: drv.mcp.tap(args.x, args.y),
    )


async def _android_double_click(
    ctx: ToolContext,
    args: AndroidDoubleClickArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.double_click",
        target_uri=f"android:doubleTap@{args.x},{args.y}",
        args_summary={"x": args.x, "y": args.y},
        coro_factory=lambda: drv.double_click(args.x, args.y),
    )


async def _android_long_press(
    ctx: ToolContext,
    args: AndroidLongPressArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.long_press",
        target_uri=f"android:longPress@{args.x},{args.y}",
        args_summary={"x": args.x, "y": args.y, "duration_ms": args.duration_ms},
        coro_factory=lambda: drv.long_press(args.x, args.y, duration_ms=args.duration_ms),
    )


async def _android_type(ctx: ToolContext, args: AndroidTypeArgs) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _run() -> None:
        if args.clear_first:
            await drv.clear_text()
        await drv.type_text(args.text)

    return await _invoke_mobile(
        ctx,
        action_type="android.type",
        target_uri=None,
        args_summary={"text_len": len(args.text), "clear_first": args.clear_first},
        coro_factory=_run,
    )


async def _android_clear_text(
    ctx: ToolContext,
    args: AndroidClearTextArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.clear_text",
        target_uri=None,
        args_summary={},
        coro_factory=lambda: drv.clear_text(),
    )


async def _android_swipe(ctx: ToolContext, args: AndroidSwipeArgs) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.swipe",
        target_uri=None,
        args_summary={
            "start": (args.start_x, args.start_y),
            "end": (args.end_x, args.end_y),
            "duration_ms": args.duration_ms,
        },
        coro_factory=lambda: drv.swipe(
            args.start_x,
            args.start_y,
            args.end_x,
            args.end_y,
            duration_ms=args.duration_ms,
        ),
    )


async def _android_scroll(ctx: ToolContext, args: AndroidScrollArgs) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.scroll",
        target_uri=None,
        args_summary={"direction": args.direction, "amount": args.amount},
        coro_factory=lambda: drv.scroll(direction=args.direction, amount=args.amount),
    )


async def _android_press_key(
    ctx: ToolContext,
    args: AndroidPressKeyArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.press_key",
        target_uri=None,
        args_summary={"key": args.key},
        coro_factory=lambda: drv.press_key(args.key),
    )


async def _android_pinch(ctx: ToolContext, args: AndroidPinchArgs) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.pinch",
        target_uri=None,
        args_summary={"scale": args.scale, "velocity": args.velocity},
        coro_factory=lambda: drv.pinch(args.scale, velocity=args.velocity),
    )


def build_android_interaction_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="android_click",
            description="Tap on Android at pixel (x, y). Top-of-loop interaction.",
            args_model=AndroidClickArgs,
            handler=_android_click,
            defer_loading=False,
        ),
        ToolSpec(
            name="android_type",
            description="Type text into the active Android field.",
            args_model=AndroidTypeArgs,
            handler=_android_type,
            defer_loading=False,
        ),
        ToolSpec(
            name="android_swipe",
            description="Swipe between two pixel coords with duration (ms).",
            args_model=AndroidSwipeArgs,
            handler=_android_swipe,
            defer_loading=False,
        ),
        ToolSpec(
            name="android_press_key",
            description=(
                "Press an Android hardware/system key: back, home, menu, "
                "app_switch, power, volume_up, volume_down."
            ),
            args_model=AndroidPressKeyArgs,
            handler=_android_press_key,
            defer_loading=False,
        ),
        ToolSpec(
            name="android_scroll",
            description="Scroll the active Android surface by direction + amount.",
            args_model=AndroidScrollArgs,
            handler=_android_scroll,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_double_click",
            description="Double-tap at pixel (x, y) on Android.",
            args_model=AndroidDoubleClickArgs,
            handler=_android_double_click,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_long_press",
            description="Long-press at (x, y) for duration_ms on Android.",
            args_model=AndroidLongPressArgs,
            handler=_android_long_press,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_clear_text",
            description="Clear text from the active Android input field.",
            args_model=AndroidClearTextArgs,
            handler=_android_clear_text,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_pinch",
            description=(
                "Pinch gesture on Android (emulated via two opposing swipes; "
                "scale < 1 zoom out, > 1 zoom in)."
            ),
            args_model=AndroidPinchArgs,
            handler=_android_pinch,
            defer_loading=True,
        ),
    ]
