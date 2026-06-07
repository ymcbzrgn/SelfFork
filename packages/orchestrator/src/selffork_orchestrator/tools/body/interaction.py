"""Body interaction tools — click / type / scroll / swipe / press_key.

Five tools that mutate the active surface. All gated through the
warden; targets / coordinates / text length surface to the audit log.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import (
    ToolArgs,
    ToolContext,
    ToolSpec,
)
from selffork_orchestrator.tools.body._internal import _invoke, _require_driver

__all__ = [
    "BodyClickArgs",
    "BodyPressKeyArgs",
    "BodyScrollArgs",
    "BodySwipeArgs",
    "BodyTypeArgs",
    "build_interaction_tools",
]


class BodyClickArgs(ToolArgs):
    target: str = Field(
        min_length=1,
        description="Element selector or natural-language description",
    )
    bbox: tuple[int, int, int, int] | None = None
    button: Literal["left", "right"] = "left"


class BodyTypeArgs(ToolArgs):
    text: str
    target: str | None = None


class BodyScrollArgs(ToolArgs):
    direction: Literal["up", "down", "top", "bottom", "left", "right"] = "down"
    amount: int = Field(default=300, ge=10, le=10000)


class BodySwipeArgs(ToolArgs):
    start_x: int = Field(ge=0)
    start_y: int = Field(ge=0)
    end_x: int = Field(ge=0)
    end_y: int = Field(ge=0)
    duration_ms: int = Field(default=250, ge=50, le=5000)


class BodyPressKeyArgs(ToolArgs):
    key_combo: str = Field(min_length=1, max_length=64)


async def _body_click(ctx: ToolContext, args: BodyClickArgs) -> dict[str, Any]:
    driver = _require_driver(ctx)
    return await _invoke(
        ctx,
        action_type="click",
        target_uri=args.target,
        args_summary={"bbox": args.bbox, "button": args.button},
        coro_factory=lambda: driver.click(
            args.target,
            bbox=args.bbox,
            button=args.button,
        ),
    )


async def _body_type(ctx: ToolContext, args: BodyTypeArgs) -> dict[str, Any]:
    driver = _require_driver(ctx)
    return await _invoke(
        ctx,
        action_type="type",
        target_uri=args.target,
        args_summary={"text_len": len(args.text)},
        coro_factory=lambda: driver.type_text(args.text, target=args.target),
    )


async def _body_scroll(ctx: ToolContext, args: BodyScrollArgs) -> dict[str, Any]:
    driver = _require_driver(ctx)
    return await _invoke(
        ctx,
        action_type="scroll",
        target_uri=None,
        args_summary={"direction": args.direction, "amount": args.amount},
        coro_factory=lambda: driver.scroll(
            direction=args.direction,
            amount=args.amount,
        ),
    )


async def _body_swipe(ctx: ToolContext, args: BodySwipeArgs) -> dict[str, Any]:
    driver = _require_driver(ctx)
    return await _invoke(
        ctx,
        action_type="swipe",
        target_uri=None,
        args_summary={
            "start": (args.start_x, args.start_y),
            "end": (args.end_x, args.end_y),
            "duration_ms": args.duration_ms,
        },
        coro_factory=lambda: driver.swipe(
            args.start_x,
            args.start_y,
            args.end_x,
            args.end_y,
            duration_ms=args.duration_ms,
        ),
    )


async def _body_press_key(
    ctx: ToolContext,
    args: BodyPressKeyArgs,
) -> dict[str, Any]:
    driver = _require_driver(ctx)
    return await _invoke(
        ctx,
        action_type="press_key",
        target_uri=None,
        args_summary={"key_combo": args.key_combo},
        coro_factory=lambda: driver.press_key(args.key_combo),
    )


def build_interaction_tools() -> list[ToolSpec[Any]]:
    """Five interaction tools — click / type / scroll / swipe / press_key."""
    return [
        ToolSpec(
            name="body_click",
            description=("Click on a UI element via vision/AX-tree locator (T1)."),
            args_model=BodyClickArgs,
            handler=_body_click,
        ),
        ToolSpec(
            name="body_type",
            description=("Type text into the active or specified target field (T1)."),
            args_model=BodyTypeArgs,
            handler=_body_type,
        ),
        ToolSpec(
            name="body_scroll",
            description=("Scroll the active surface by direction + amount (T0)."),
            args_model=BodyScrollArgs,
            handler=_body_scroll,
        ),
        ToolSpec(
            name="body_swipe",
            description=("Swipe gesture between two points with duration (T1)."),
            args_model=BodySwipeArgs,
            handler=_body_swipe,
        ),
        ToolSpec(
            name="body_press_key",
            description=("Press a key combination such as 'cmd+t' or 'back' (T1)."),
            args_model=BodyPressKeyArgs,
            handler=_body_press_key,
        ),
    ]
