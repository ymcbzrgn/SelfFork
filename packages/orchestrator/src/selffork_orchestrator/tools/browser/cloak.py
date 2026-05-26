"""Browser cloak/stealth tools — user_agent/headers/stealth/proxy/clear_cache (5 tools)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.browser._internal import (
    _invoke_browser,
    _require_browser_driver,
)

__all__ = [
    "BrowserClearCacheArgs",
    "BrowserEnableStealthArgs",
    "BrowserSetExtraHeadersArgs",
    "BrowserSetProxyArgs",
    "BrowserSetUserAgentArgs",
    "build_browser_cloak_tools",
]


class BrowserSetUserAgentArgs(ToolArgs):
    user_agent: str = Field(min_length=1, max_length=512)


class BrowserSetExtraHeadersArgs(ToolArgs):
    headers: dict[str, str] = Field(min_length=1)


class BrowserEnableStealthArgs(ToolArgs):
    pass


class BrowserSetProxyArgs(ToolArgs):
    server: str = Field(min_length=1, max_length=256)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=128)


class BrowserClearCacheArgs(ToolArgs):
    pass


async def _browser_set_user_agent(
    ctx: ToolContext, args: BrowserSetUserAgentArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx, action_type="browser.set_user_agent", target_uri=None,
        args_summary={"ua_len": len(args.user_agent)},
        coro_factory=lambda: drv.set_user_agent(args.user_agent),
    )


async def _browser_set_extra_headers(
    ctx: ToolContext, args: BrowserSetExtraHeadersArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx, action_type="browser.set_extra_headers", target_uri=None,
        args_summary={"header_count": len(args.headers)},
        coro_factory=lambda: drv.set_extra_headers(args.headers),
    )


async def _browser_enable_stealth(
    ctx: ToolContext, args: BrowserEnableStealthArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx, action_type="browser.enable_stealth", target_uri=None,
        args_summary={}, coro_factory=lambda: drv.enable_stealth(),
    )


async def _browser_set_proxy(
    ctx: ToolContext, args: BrowserSetProxyArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx, action_type="browser.set_proxy", target_uri=args.server,
        args_summary={"server": args.server, "auth": args.username is not None},
        coro_factory=lambda: drv.set_proxy(args.server, args.username, args.password),
    )


async def _browser_clear_cache(
    ctx: ToolContext, args: BrowserClearCacheArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx, action_type="browser.clear_cache", target_uri=None,
        args_summary={}, coro_factory=lambda: drv.clear_cache(),
    )


def build_browser_cloak_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(name="browser_set_user_agent", description="Override the navigator.userAgent + UA header.",  # noqa: E501
                 args_model=BrowserSetUserAgentArgs, handler=_browser_set_user_agent, defer_loading=True),  # noqa: E501
        ToolSpec(name="browser_set_extra_headers", description="Set extra HTTP headers for outgoing requests.",  # noqa: E501
                 args_model=BrowserSetExtraHeadersArgs, handler=_browser_set_extra_headers, defer_loading=True),  # noqa: E501
        ToolSpec(name="browser_enable_stealth",
                 description="Inject baseline stealth init scripts (webdriver/plugins/lang).",
                 args_model=BrowserEnableStealthArgs, handler=_browser_enable_stealth, defer_loading=True),  # noqa: E501
        ToolSpec(name="browser_set_proxy",
                 description="Configure proxy server for the next browser start cycle.",
                 args_model=BrowserSetProxyArgs, handler=_browser_set_proxy, defer_loading=True),
        ToolSpec(name="browser_clear_cache",
                 description="Clear browser cache + cookies via CDP (Chromium only).",
                 args_model=BrowserClearCacheArgs, handler=_browser_clear_cache, defer_loading=True),  # noqa: E501
    ]
