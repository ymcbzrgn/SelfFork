"""Browser storage tools — cookies + localStorage + storage_state (6 tools)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.browser._internal import (
    _invoke_browser,
    _require_browser_driver,
)

__all__ = [
    "BrowserCookiesClearArgs",
    "BrowserCookiesGetArgs",
    "BrowserCookiesSetArgs",
    "BrowserLocalStorageClearArgs",
    "BrowserLocalStorageGetArgs",
    "BrowserLocalStorageSetArgs",
    "build_browser_storage_tools",
]


class BrowserCookiesGetArgs(ToolArgs):
    url: str | None = Field(default=None, max_length=4096)


class BrowserCookiesSetArgs(ToolArgs):
    cookies: list[dict[str, Any]] = Field(min_length=1)


class BrowserCookiesClearArgs(ToolArgs):
    pass


class BrowserLocalStorageGetArgs(ToolArgs):
    key: str = Field(min_length=1, max_length=512)


class BrowserLocalStorageSetArgs(ToolArgs):
    key: str = Field(min_length=1, max_length=512)
    value: str = Field(max_length=100_000)


class BrowserLocalStorageClearArgs(ToolArgs):
    pass


async def _browser_cookies_get(ctx: ToolContext, args: BrowserCookiesGetArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _get() -> dict[str, Any]:
        cookies = await drv.cookies_get(args.url)
        return {"count": len(cookies), "cookies": cookies[:100]}

    return await _invoke_browser(
        ctx, action_type="browser.cookies_get", target_uri=args.url,
        args_summary={"url": args.url}, coro_factory=_get,
    )


async def _browser_cookies_set(ctx: ToolContext, args: BrowserCookiesSetArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx, action_type="browser.cookies_set", target_uri=None,
        args_summary={"count": len(args.cookies)},
        coro_factory=lambda: drv.cookies_set(args.cookies),
    )


async def _browser_cookies_clear(
    ctx: ToolContext, args: BrowserCookiesClearArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx, action_type="browser.cookies_clear", target_uri=None,
        args_summary={}, coro_factory=lambda: drv.cookies_clear(),
    )


async def _browser_local_storage_get(
    ctx: ToolContext, args: BrowserLocalStorageGetArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _get() -> dict[str, Any]:
        value = await drv.local_storage_get(args.key)
        return {"key": args.key, "value": value}

    return await _invoke_browser(
        ctx, action_type="browser.local_storage_get", target_uri=f"ls:{args.key}",
        args_summary={"key": args.key}, coro_factory=_get,
    )


async def _browser_local_storage_set(
    ctx: ToolContext, args: BrowserLocalStorageSetArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx, action_type="browser.local_storage_set", target_uri=f"ls:{args.key}",
        args_summary={"key": args.key, "value_len": len(args.value)},
        coro_factory=lambda: drv.local_storage_set(args.key, args.value),
    )


async def _browser_local_storage_clear(
    ctx: ToolContext, args: BrowserLocalStorageClearArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx, action_type="browser.local_storage_clear", target_uri=None,
        args_summary={}, coro_factory=lambda: drv.local_storage_clear(),
    )


def build_browser_storage_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(name="browser_cookies_get", description="Read cookies (optionally scoped by URL).",
                 args_model=BrowserCookiesGetArgs, handler=_browser_cookies_get, defer_loading=True),  # noqa: E501
        ToolSpec(name="browser_cookies_set", description="Set one or more cookies.",
                 args_model=BrowserCookiesSetArgs, handler=_browser_cookies_set, defer_loading=True),  # noqa: E501
        ToolSpec(name="browser_cookies_clear", description="Clear all cookies in the active context.",  # noqa: E501
                 args_model=BrowserCookiesClearArgs, handler=_browser_cookies_clear, defer_loading=True),  # noqa: E501
        ToolSpec(name="browser_local_storage_get", description="Read a localStorage key on the active page.",  # noqa: E501
                 args_model=BrowserLocalStorageGetArgs, handler=_browser_local_storage_get, defer_loading=True),  # noqa: E501
        ToolSpec(name="browser_local_storage_set", description="Write a localStorage key on the active page.",  # noqa: E501
                 args_model=BrowserLocalStorageSetArgs, handler=_browser_local_storage_set, defer_loading=True),  # noqa: E501
        ToolSpec(name="browser_local_storage_clear", description="Clear localStorage on the active page.",  # noqa: E501
                 args_model=BrowserLocalStorageClearArgs, handler=_browser_local_storage_clear, defer_loading=True),  # noqa: E501
    ]
