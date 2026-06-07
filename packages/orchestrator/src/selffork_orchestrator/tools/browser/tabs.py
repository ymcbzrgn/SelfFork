"""Browser tab tools — new/close/list/switch/get_active/duplicate (6 tools)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.browser._internal import (
    _invoke_browser,
    _require_browser_driver,
)

__all__ = [
    "BrowserCloseTabArgs",
    "BrowserDuplicateTabArgs",
    "BrowserGetActiveTabArgs",
    "BrowserListTabsArgs",
    "BrowserNewTabArgs",
    "BrowserSwitchTabArgs",
    "build_browser_tabs_tools",
]


class BrowserNewTabArgs(ToolArgs):
    url: str | None = Field(default=None, max_length=8192)


class BrowserCloseTabArgs(ToolArgs):
    index: int | None = Field(default=None, ge=0)


class BrowserListTabsArgs(ToolArgs):
    pass


class BrowserSwitchTabArgs(ToolArgs):
    index: int = Field(ge=0)


class BrowserGetActiveTabArgs(ToolArgs):
    pass


class BrowserDuplicateTabArgs(ToolArgs):
    pass


async def _browser_new_tab(ctx: ToolContext, args: BrowserNewTabArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _open() -> dict[str, Any]:
        index = await drv.new_tab(args.url)
        return {"index": index, "url": args.url}

    return await _invoke_browser(
        ctx,
        action_type="browser.new_tab",
        target_uri=args.url,
        args_summary={"url": args.url},
        coro_factory=_open,
    )


async def _browser_close_tab(ctx: ToolContext, args: BrowserCloseTabArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _close() -> dict[str, Any]:
        remaining = await drv.close_tab(args.index)
        return {"remaining": remaining}

    return await _invoke_browser(
        ctx,
        action_type="browser.close_tab",
        target_uri=None,
        args_summary={"index": args.index},
        coro_factory=_close,
    )


async def _browser_list_tabs(ctx: ToolContext, args: BrowserListTabsArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _list() -> dict[str, Any]:
        tabs = await drv.list_tabs()
        return {"count": len(tabs), "tabs": tabs}

    return await _invoke_browser(
        ctx,
        action_type="browser.list_tabs",
        target_uri=None,
        args_summary={},
        coro_factory=_list,
    )


async def _browser_switch_tab(ctx: ToolContext, args: BrowserSwitchTabArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _switch() -> dict[str, Any]:
        out: dict[str, Any] = await drv.switch_tab(args.index)
        return out

    return await _invoke_browser(
        ctx,
        action_type="browser.switch_tab",
        target_uri=None,
        args_summary={"index": args.index},
        coro_factory=_switch,
    )


async def _browser_get_active_tab(
    ctx: ToolContext,
    args: BrowserGetActiveTabArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _active() -> dict[str, Any]:
        out: dict[str, Any] = await drv.get_active_tab()
        return out

    return await _invoke_browser(
        ctx,
        action_type="browser.get_active_tab",
        target_uri=None,
        args_summary={},
        coro_factory=_active,
    )


async def _browser_duplicate_tab(
    ctx: ToolContext,
    args: BrowserDuplicateTabArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _dup() -> dict[str, Any]:
        index = await drv.duplicate_tab()
        return {"index": index}

    return await _invoke_browser(
        ctx,
        action_type="browser.duplicate_tab",
        target_uri=None,
        args_summary={},
        coro_factory=_dup,
    )


def build_browser_tabs_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="browser_new_tab",
            description="Open a new tab, optionally navigating to URL.",  # noqa: E501
            args_model=BrowserNewTabArgs,
            handler=_browser_new_tab,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_close_tab",
            description="Close the active tab (or by index).",
            args_model=BrowserCloseTabArgs,
            handler=_browser_close_tab,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_list_tabs",
            description="List all open tabs (index/url/title).",
            args_model=BrowserListTabsArgs,
            handler=_browser_list_tabs,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_switch_tab",
            description="Activate the tab at the given index.",
            args_model=BrowserSwitchTabArgs,
            handler=_browser_switch_tab,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_get_active_tab",
            description="Return descriptor of the currently active tab.",  # noqa: E501
            args_model=BrowserGetActiveTabArgs,
            handler=_browser_get_active_tab,
            defer_loading=True,
        ),  # noqa: E501
        ToolSpec(
            name="browser_duplicate_tab",
            description="Duplicate the active tab (clone URL).",
            args_model=BrowserDuplicateTabArgs,
            handler=_browser_duplicate_tab,
            defer_loading=True,
        ),  # noqa: E501
    ]
