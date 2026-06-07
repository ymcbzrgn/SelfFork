"""Browser navigation tools — navigate/back/forward/reload/get_url/title/viewport/wait."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.browser._internal import (
    _invoke_browser,
    _require_browser_driver,
)

__all__ = [
    "BrowserBackArgs",
    "BrowserForwardArgs",
    "BrowserGetTitleArgs",
    "BrowserGetUrlArgs",
    "BrowserNavigateArgs",
    "BrowserReloadArgs",
    "BrowserSetViewportArgs",
    "BrowserWaitForLoadStateArgs",
    "BrowserWaitForUrlArgs",
    "build_browser_navigation_tools",
]


class BrowserNavigateArgs(ToolArgs):
    url: str = Field(min_length=1, max_length=8192)


class BrowserBackArgs(ToolArgs):
    pass


class BrowserForwardArgs(ToolArgs):
    pass


class BrowserReloadArgs(ToolArgs):
    pass


class BrowserGetUrlArgs(ToolArgs):
    pass


class BrowserGetTitleArgs(ToolArgs):
    pass


class BrowserSetViewportArgs(ToolArgs):
    width: int = Field(ge=320, le=10_000)
    height: int = Field(ge=320, le=10_000)


class BrowserWaitForLoadStateArgs(ToolArgs):
    state: Literal["load", "domcontentloaded", "networkidle"] = "load"
    timeout: float = Field(default=30.0, ge=0.1, le=300.0)


class BrowserWaitForUrlArgs(ToolArgs):
    url_pattern: str = Field(min_length=1, max_length=4096)
    timeout: float = Field(default=30.0, ge=0.1, le=300.0)


async def _browser_navigate(ctx: ToolContext, args: BrowserNavigateArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.navigate",
        target_uri=args.url,
        args_summary={"url": args.url},
        coro_factory=lambda: drv.goto(args.url),
    )


async def _browser_back(ctx: ToolContext, args: BrowserBackArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.back",
        target_uri=None,
        args_summary={},
        coro_factory=lambda: drv.back(),
    )


async def _browser_forward(ctx: ToolContext, args: BrowserForwardArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.forward",
        target_uri=None,
        args_summary={},
        coro_factory=lambda: drv.forward(),
    )


async def _browser_reload(ctx: ToolContext, args: BrowserReloadArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.reload",
        target_uri=None,
        args_summary={},
        coro_factory=lambda: drv.reload(),
    )


async def _browser_get_url(ctx: ToolContext, args: BrowserGetUrlArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _get() -> dict[str, Any]:
        return {"url": await drv.get_url()}

    return await _invoke_browser(
        ctx,
        action_type="browser.get_url",
        target_uri=None,
        args_summary={},
        coro_factory=_get,
    )


async def _browser_get_title(ctx: ToolContext, args: BrowserGetTitleArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _get() -> dict[str, Any]:
        return {"title": await drv.get_title()}

    return await _invoke_browser(
        ctx,
        action_type="browser.get_title",
        target_uri=None,
        args_summary={},
        coro_factory=_get,
    )


async def _browser_set_viewport(ctx: ToolContext, args: BrowserSetViewportArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.set_viewport",
        target_uri=None,
        args_summary={"width": args.width, "height": args.height},
        coro_factory=lambda: drv.set_viewport(args.width, args.height),
    )


async def _browser_wait_for_load_state(
    ctx: ToolContext,
    args: BrowserWaitForLoadStateArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.wait_for_load_state",
        target_uri=None,
        args_summary={"state": args.state, "timeout": args.timeout},
        coro_factory=lambda: drv.wait_for_load_state(args.state, timeout=args.timeout),
    )


async def _browser_wait_for_url(
    ctx: ToolContext,
    args: BrowserWaitForUrlArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.wait_for_url",
        target_uri=args.url_pattern,
        args_summary={"url_pattern": args.url_pattern, "timeout": args.timeout},
        coro_factory=lambda: drv.wait_for_url(args.url_pattern, timeout=args.timeout),
    )


def build_browser_navigation_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="browser_navigate",
            description="Navigate the active tab to a URL (security-watchdog gated).",
            args_model=BrowserNavigateArgs,
            handler=_browser_navigate,
            defer_loading=False,
        ),
        ToolSpec(
            name="browser_get_url",
            description="Read the active tab's current URL.",
            args_model=BrowserGetUrlArgs,
            handler=_browser_get_url,
            defer_loading=False,
        ),
        ToolSpec(
            name="browser_wait_for_load_state",
            description="Wait for load|domcontentloaded|networkidle on the active tab.",
            args_model=BrowserWaitForLoadStateArgs,
            handler=_browser_wait_for_load_state,
            defer_loading=False,
        ),
        ToolSpec(
            name="browser_back",
            description="Navigate back in the active tab's history.",
            args_model=BrowserBackArgs,
            handler=_browser_back,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_forward",
            description="Navigate forward in the active tab's history.",
            args_model=BrowserForwardArgs,
            handler=_browser_forward,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_reload",
            description="Reload the active tab.",
            args_model=BrowserReloadArgs,
            handler=_browser_reload,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_get_title",
            description="Read the active tab's document title.",
            args_model=BrowserGetTitleArgs,
            handler=_browser_get_title,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_set_viewport",
            description="Resize the active page viewport (width, height in CSS px).",
            args_model=BrowserSetViewportArgs,
            handler=_browser_set_viewport,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_wait_for_url",
            description="Wait until the active tab's URL matches a pattern.",
            args_model=BrowserWaitForUrlArgs,
            handler=_browser_wait_for_url,
            defer_loading=True,
        ),
    ]
