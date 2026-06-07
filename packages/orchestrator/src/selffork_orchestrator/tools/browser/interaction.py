"""Browser interaction tools — click/type/swipe/hover/select/check/upload/drag (10 tools)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.browser._internal import (
    _invoke_browser,
    _require_browser_driver,
)

__all__ = [
    "BrowserCheckArgs",
    "BrowserClickArgs",
    "BrowserDoubleClickArgs",
    "BrowserDragAndDropArgs",
    "BrowserFillFormArgs",
    "BrowserHoverArgs",
    "BrowserPressKeyArgs",
    "BrowserSelectOptionArgs",
    "BrowserTypeArgs",
    "BrowserUncheckArgs",
    "BrowserUploadFileArgs",
    "build_browser_interaction_tools",
]


class BrowserClickArgs(ToolArgs):
    target: str | None = Field(
        default=None, max_length=1024, description="CSS selector or text content"
    )  # noqa: E501
    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)
    button: Literal["left", "right"] = "left"


class BrowserDoubleClickArgs(ToolArgs):
    target: str | None = Field(default=None, max_length=1024)
    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)


class BrowserTypeArgs(ToolArgs):
    text: str = Field(min_length=1, max_length=10_000)
    target: str | None = Field(default=None, max_length=1024)
    clear_first: bool = False


class BrowserFillFormArgs(ToolArgs):
    fields: dict[str, str] = Field(min_length=1)


class BrowserHoverArgs(ToolArgs):
    target: str | None = Field(default=None, max_length=1024)
    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)


class BrowserPressKeyArgs(ToolArgs):
    key: str = Field(min_length=1, max_length=64, description="e.g. 'Enter', 'Control+a'")


class BrowserSelectOptionArgs(ToolArgs):
    target: str = Field(min_length=1, max_length=1024)
    value: str | list[str] | None = None
    label: str | None = None
    index: int | None = None


class BrowserCheckArgs(ToolArgs):
    target: str = Field(min_length=1, max_length=1024)


class BrowserUncheckArgs(ToolArgs):
    target: str = Field(min_length=1, max_length=1024)


class BrowserDragAndDropArgs(ToolArgs):
    source: str = Field(min_length=1, max_length=1024)
    target: str = Field(min_length=1, max_length=1024)


class BrowserUploadFileArgs(ToolArgs):
    target: str = Field(min_length=1, max_length=1024)
    file_path: str | list[str] = Field(description="Host path(s) to upload")


async def _browser_click(ctx: ToolContext, args: BrowserClickArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    target_uri = args.target or f"coords:{args.x},{args.y}"

    async def _run() -> None:
        if args.x is not None and args.y is not None:
            await drv.click(
                target=args.target or "", bbox=(args.x, args.y, 1, 1), button=args.button
            )  # noqa: E501
        elif args.target is not None:
            await drv.click(args.target, button=args.button)
        else:
            raise ValueError("browser_click requires target or (x, y)")

    return await _invoke_browser(
        ctx,
        action_type="browser.click",
        target_uri=target_uri,
        args_summary={"target": args.target, "x": args.x, "y": args.y, "button": args.button},
        coro_factory=_run,
    )


async def _browser_double_click(ctx: ToolContext, args: BrowserDoubleClickArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.double_click",
        target_uri=args.target or f"coords:{args.x},{args.y}",
        args_summary={"target": args.target, "x": args.x, "y": args.y},
        coro_factory=lambda: drv.double_click(target=args.target, x=args.x, y=args.y),
    )


async def _browser_type(ctx: ToolContext, args: BrowserTypeArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _run() -> None:
        if args.clear_first and args.target:
            await drv.clear(args.target)
        await drv.type_text(args.text, target=args.target)

    return await _invoke_browser(
        ctx,
        action_type="browser.type",
        target_uri=args.target,
        args_summary={
            "text_len": len(args.text),
            "target": args.target,
            "clear_first": args.clear_first,
        },  # noqa: E501
        coro_factory=_run,
    )


async def _browser_fill_form(ctx: ToolContext, args: BrowserFillFormArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _run() -> dict[str, Any]:
        filled = await drv.fill_form(args.fields)
        return {"filled": filled, "total": len(args.fields)}

    return await _invoke_browser(
        ctx,
        action_type="browser.fill_form",
        target_uri=None,
        args_summary={"field_count": len(args.fields)},
        coro_factory=_run,
    )


async def _browser_hover(ctx: ToolContext, args: BrowserHoverArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.hover",
        target_uri=args.target or f"coords:{args.x},{args.y}",
        args_summary={"target": args.target, "x": args.x, "y": args.y},
        coro_factory=lambda: drv.hover(target=args.target, x=args.x, y=args.y),
    )


async def _browser_press_key(ctx: ToolContext, args: BrowserPressKeyArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.press_key",
        target_uri=None,
        args_summary={"key": args.key},
        coro_factory=lambda: drv.press_key(args.key),
    )


async def _browser_select_option(ctx: ToolContext, args: BrowserSelectOptionArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _run() -> dict[str, Any]:
        selected = await drv.select_option(
            args.target,
            value=args.value,
            label=args.label,
            index=args.index,
        )
        return {"selected": selected}

    return await _invoke_browser(
        ctx,
        action_type="browser.select_option",
        target_uri=args.target,
        args_summary={"value": args.value, "label": args.label, "index": args.index},
        coro_factory=_run,
    )


async def _browser_check(ctx: ToolContext, args: BrowserCheckArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.check",
        target_uri=args.target,
        args_summary={"target": args.target},
        coro_factory=lambda: drv.check(args.target),
    )


async def _browser_uncheck(ctx: ToolContext, args: BrowserUncheckArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.uncheck",
        target_uri=args.target,
        args_summary={"target": args.target},
        coro_factory=lambda: drv.uncheck(args.target),
    )


async def _browser_drag_and_drop(ctx: ToolContext, args: BrowserDragAndDropArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.drag_and_drop",
        target_uri=f"drag:{args.source[:32]}→{args.target[:32]}",
        args_summary={"source": args.source, "target": args.target},
        coro_factory=lambda: drv.drag_and_drop(args.source, args.target),
    )


async def _browser_upload_file(ctx: ToolContext, args: BrowserUploadFileArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    paths = args.file_path if isinstance(args.file_path, list) else [args.file_path]
    return await _invoke_browser(
        ctx,
        action_type="browser.upload_file",
        target_uri=args.target,
        args_summary={"target": args.target, "file_count": len(paths)},
        coro_factory=lambda: drv.upload_file(args.target, args.file_path),
    )


def build_browser_interaction_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="browser_click",
            description="Click a CSS selector / text / pixel (x,y) on the active page.",
            args_model=BrowserClickArgs,
            handler=_browser_click,
            defer_loading=False,
        ),
        ToolSpec(
            name="browser_type",
            description="Type text into a selector (clear_first optional) or the focused element.",
            args_model=BrowserTypeArgs,
            handler=_browser_type,
            defer_loading=False,
        ),
        ToolSpec(
            name="browser_press_key",
            description=("Press a key combo on the active page (e.g. 'Enter', 'Control+a')."),
            args_model=BrowserPressKeyArgs,
            handler=_browser_press_key,
            defer_loading=False,
        ),
        ToolSpec(
            name="browser_double_click",
            description="Double-click a selector or pixel (x, y).",
            args_model=BrowserDoubleClickArgs,
            handler=_browser_double_click,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_hover",
            description="Hover the pointer over a selector or pixel.",
            args_model=BrowserHoverArgs,
            handler=_browser_hover,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_fill_form",
            description="Fill multiple form fields {selector: value}. Returns filled count.",
            args_model=BrowserFillFormArgs,
            handler=_browser_fill_form,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_select_option",
            description="Select <select> option by value, label, or index.",
            args_model=BrowserSelectOptionArgs,
            handler=_browser_select_option,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_check",
            description="Check a checkbox / radio (Playwright .check).",
            args_model=BrowserCheckArgs,
            handler=_browser_check,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_uncheck",
            description="Uncheck a checkbox (Playwright .uncheck).",
            args_model=BrowserUncheckArgs,
            handler=_browser_uncheck,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_drag_and_drop",
            description="Drag from source selector and drop onto target selector.",
            args_model=BrowserDragAndDropArgs,
            handler=_browser_drag_and_drop,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_upload_file",
            description="Upload host file(s) to a <input type=file> selector.",
            args_model=BrowserUploadFileArgs,
            handler=_browser_upload_file,
            defer_loading=True,
        ),
    ]
