"""iOS element-query tools — find_element / get_active_element (2 tools)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_ios_driver,
)

__all__ = [
    "IosFindElementArgs",
    "IosGetActiveElementArgs",
    "build_ios_element_tools",
]


class IosFindElementArgs(ToolArgs):
    by: Literal[
        "accessibility id", "name", "class name", "xpath", "predicate string", "ios class chain",
    ] = "accessibility id"
    value: str = Field(min_length=1, max_length=4_096)


class IosGetActiveElementArgs(ToolArgs):
    pass


async def _ios_find_element(ctx: ToolContext, args: IosFindElementArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _find() -> dict[str, Any]:
        result: dict[str, Any] = await drv.find_element(args.by, args.value)
        return result

    return await _invoke_mobile(
        ctx,
        action_type="ios.find_element",
        target_uri=f"ios-locator:{args.by}={args.value[:64]}",
        args_summary={"by": args.by, "value_len": len(args.value)},
        coro_factory=_find,
    )


async def _ios_get_active_element(
    ctx: ToolContext, args: IosGetActiveElementArgs,
) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _active() -> dict[str, Any]:
        result: dict[str, Any] = await drv.get_active_element()
        return result

    return await _invoke_mobile(
        ctx,
        action_type="ios.get_active_element",
        target_uri=None,
        args_summary={},
        coro_factory=_active,
    )


def build_ios_element_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="ios_find_element",
            description=(
                "Find an iOS element via accessibility id, name, xpath, "
                "predicate, or class chain. Returns id/tag/text/state/rect."
            ),
            args_model=IosFindElementArgs,
            handler=_ios_find_element,
            defer_loading=True,
        ),
        ToolSpec(
            name="ios_get_active_element",
            description="Return descriptor of the currently focused iOS element.",
            args_model=IosGetActiveElementArgs,
            handler=_ios_get_active_element,
            defer_loading=True,
        ),
    ]
