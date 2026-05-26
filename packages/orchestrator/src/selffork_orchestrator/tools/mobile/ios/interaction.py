"""iOS interaction tools — tap/type/swipe/scroll/gesture/key (9 tools)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_ios_driver,
)

__all__ = [
    "IosClearTextArgs",
    "IosClickArgs",
    "IosDoubleClickArgs",
    "IosLongPressArgs",
    "IosPinchArgs",
    "IosPressKeyArgs",
    "IosScrollArgs",
    "IosSwipeArgs",
    "IosTypeArgs",
    "build_ios_interaction_tools",
]


class IosClickArgs(ToolArgs):
    x: int = Field(ge=0, description="Pixel x (screen coords)")
    y: int = Field(ge=0, description="Pixel y (screen coords)")


class IosDoubleClickArgs(ToolArgs):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class IosLongPressArgs(ToolArgs):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    duration_ms: int = Field(default=800, ge=100, le=10_000)


class IosTypeArgs(ToolArgs):
    text: str = Field(min_length=1, max_length=10_000)
    clear_first: bool = False


class IosClearTextArgs(ToolArgs):
    pass


class IosSwipeArgs(ToolArgs):
    start_x: int = Field(ge=0)
    start_y: int = Field(ge=0)
    end_x: int = Field(ge=0)
    end_y: int = Field(ge=0)
    duration_ms: int = Field(default=250, ge=50, le=5_000)


class IosScrollArgs(ToolArgs):
    direction: Literal["up", "down", "left", "right"] = "down"
    amount: int = Field(default=300, ge=10, le=10_000)


class IosPressKeyArgs(ToolArgs):
    key: Literal[
        "home", "lock", "volumeup", "volumedown", "siri",
    ] = Field(description="iOS hardware button / key")


class IosPinchArgs(ToolArgs):
    scale: float = Field(ge=0.1, le=10.0, description="Pinch scale; <1 zoom out, >1 zoom in")
    velocity: float = Field(default=1.0, ge=0.1, le=10.0)


async def _ios_click(ctx: ToolContext, args: IosClickArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.click",
        target_uri=f"ios:tap@{args.x},{args.y}",
        args_summary={"x": args.x, "y": args.y},
        coro_factory=lambda: drv._ready_appium().tap(args.x, args.y),
    )


async def _ios_double_click(ctx: ToolContext, args: IosDoubleClickArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.double_click",
        target_uri=f"ios:doubleTap@{args.x},{args.y}",
        args_summary={"x": args.x, "y": args.y},
        coro_factory=lambda: drv.double_click(args.x, args.y),
    )


async def _ios_long_press(ctx: ToolContext, args: IosLongPressArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.long_press",
        target_uri=f"ios:longPress@{args.x},{args.y}",
        args_summary={"x": args.x, "y": args.y, "duration_ms": args.duration_ms},
        coro_factory=lambda: drv.long_press(args.x, args.y, duration_ms=args.duration_ms),
    )


async def _ios_type(ctx: ToolContext, args: IosTypeArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _run() -> None:
        if args.clear_first:
            await drv.clear_text()
        await drv.type_text(args.text)

    return await _invoke_mobile(
        ctx,
        action_type="ios.type",
        target_uri=None,
        args_summary={"text_len": len(args.text), "clear_first": args.clear_first},
        coro_factory=_run,
    )


async def _ios_clear_text(ctx: ToolContext, args: IosClearTextArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.clear_text",
        target_uri=None,
        args_summary={},
        coro_factory=lambda: drv.clear_text(),
    )


async def _ios_swipe(ctx: ToolContext, args: IosSwipeArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.swipe",
        target_uri=None,
        args_summary={
            "start": (args.start_x, args.start_y),
            "end": (args.end_x, args.end_y),
            "duration_ms": args.duration_ms,
        },
        coro_factory=lambda: drv.swipe(
            args.start_x, args.start_y, args.end_x, args.end_y,
            duration_ms=args.duration_ms,
        ),
    )


async def _ios_scroll(ctx: ToolContext, args: IosScrollArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.scroll",
        target_uri=None,
        args_summary={"direction": args.direction, "amount": args.amount},
        coro_factory=lambda: drv.scroll(direction=args.direction, amount=args.amount),
    )


async def _ios_press_key(ctx: ToolContext, args: IosPressKeyArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.press_key",
        target_uri=None,
        args_summary={"key": args.key},
        coro_factory=lambda: drv.press_key(args.key),
    )


async def _ios_pinch(ctx: ToolContext, args: IosPinchArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="ios.pinch",
        target_uri=None,
        args_summary={"scale": args.scale, "velocity": args.velocity},
        coro_factory=lambda: drv.pinch(args.scale, velocity=args.velocity),
    )


def build_ios_interaction_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="ios_click",
            description="Tap on iOS at pixel (x, y). Top-of-loop interaction.",
            args_model=IosClickArgs,
            handler=_ios_click,
            defer_loading=False,
        ),
        ToolSpec(
            name="ios_type",
            description="Type text into the active iOS field (Appium 'mobile: type').",
            args_model=IosTypeArgs,
            handler=_ios_type,
            defer_loading=False,
        ),
        ToolSpec(
            name="ios_swipe",
            description="Swipe between two pixel coords with duration (ms).",
            args_model=IosSwipeArgs,
            handler=_ios_swipe,
            defer_loading=False,
        ),
        ToolSpec(
            name="ios_press_key",
            description=(
                "Press an iOS hardware button: home, lock, volumeup, "
                "volumedown, siri."
            ),
            args_model=IosPressKeyArgs,
            handler=_ios_press_key,
            defer_loading=False,
        ),
        ToolSpec(
            name="ios_scroll",
            description="Scroll the active iOS surface by direction + amount.",
            args_model=IosScrollArgs,
            handler=_ios_scroll,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_double_click",
            description="Double-tap at pixel (x, y) on iOS.",
            args_model=IosDoubleClickArgs,
            handler=_ios_double_click,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_long_press",
            description="Touch-and-hold at (x, y) for duration_ms.",
            args_model=IosLongPressArgs,
            handler=_ios_long_press,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_clear_text",
            description="Clear text from the active iOS input field.",
            args_model=IosClearTextArgs,
            handler=_ios_clear_text,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_pinch",
            description="Pinch gesture (scale < 1 zoom out, > 1 zoom in).",
            args_model=IosPinchArgs,
            handler=_ios_pinch,
            defer_loading=True,
        ),
    ]
