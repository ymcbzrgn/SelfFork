"""Browser network tools — intercept/mock/block/wait_for_response/get_requests (5)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.browser._internal import (
    _invoke_browser,
    _require_browser_driver,
)

__all__ = [
    "BrowserBlockUrlPatternArgs",
    "BrowserGetNetworkLogArgs",
    "BrowserInterceptRequestArgs",
    "BrowserMockResponseArgs",
    "BrowserWaitForResponseArgs",
    "build_browser_network_tools",
]


class BrowserInterceptRequestArgs(ToolArgs):
    url_pattern: str = Field(min_length=1, max_length=4096)
    mode: Literal["block", "log"] = "log"


class BrowserMockResponseArgs(ToolArgs):
    url_pattern: str = Field(min_length=1, max_length=4096)
    body: str = Field(max_length=100_000)
    status: int = Field(default=200, ge=100, le=599)
    content_type: str = "application/json"


class BrowserBlockUrlPatternArgs(ToolArgs):
    url_pattern: str = Field(min_length=1, max_length=4096)


class BrowserWaitForResponseArgs(ToolArgs):
    url_pattern: str = Field(min_length=1, max_length=4096)
    timeout: float = Field(default=30.0, ge=0.1, le=300.0)


class BrowserGetNetworkLogArgs(ToolArgs):
    pass


async def _browser_intercept_request(
    ctx: ToolContext,
    args: BrowserInterceptRequestArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.intercept_request",
        target_uri=args.url_pattern,
        args_summary={"mode": args.mode},
        coro_factory=lambda: drv.intercept_request(args.url_pattern, mode=args.mode),
    )


async def _browser_mock_response(
    ctx: ToolContext,
    args: BrowserMockResponseArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.mock_response",
        target_uri=args.url_pattern,
        args_summary={"status": args.status, "body_len": len(args.body)},
        coro_factory=lambda: drv.mock_response(
            args.url_pattern,
            args.body,
            status=args.status,
            content_type=args.content_type,
        ),
    )


async def _browser_block_url_pattern(
    ctx: ToolContext,
    args: BrowserBlockUrlPatternArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    return await _invoke_browser(
        ctx,
        action_type="browser.block_url_pattern",
        target_uri=args.url_pattern,
        args_summary={"url_pattern": args.url_pattern},
        coro_factory=lambda: drv.block_url_pattern(args.url_pattern),
    )


async def _browser_wait_for_response(
    ctx: ToolContext,
    args: BrowserWaitForResponseArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _wait() -> dict[str, Any]:
        out: dict[str, Any] = await drv.wait_for_response(args.url_pattern, timeout=args.timeout)
        return out

    return await _invoke_browser(
        ctx,
        action_type="browser.wait_for_response",
        target_uri=args.url_pattern,
        args_summary={"timeout": args.timeout},
        coro_factory=_wait,
    )


async def _browser_get_network_log(
    ctx: ToolContext,
    args: BrowserGetNetworkLogArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _get() -> dict[str, Any]:
        log = await drv.get_network_log()
        return {"count": len(log), "preview": log[:50]}

    return await _invoke_browser(
        ctx,
        action_type="browser.get_network_log",
        target_uri=None,
        args_summary={},
        coro_factory=_get,
    )


def build_browser_network_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="browser_intercept_request",
            description="Route requests matching url_pattern; log or block.",
            args_model=BrowserInterceptRequestArgs,
            handler=_browser_intercept_request,
            defer_loading=True,
        ),  # noqa: E501
        ToolSpec(
            name="browser_mock_response",
            description="Mock a response for url_pattern with body/status/content_type.",
            args_model=BrowserMockResponseArgs,
            handler=_browser_mock_response,
            defer_loading=True,
        ),  # noqa: E501
        ToolSpec(
            name="browser_block_url_pattern",
            description="Block all requests matching url_pattern.",
            args_model=BrowserBlockUrlPatternArgs,
            handler=_browser_block_url_pattern,
            defer_loading=True,
        ),  # noqa: E501
        ToolSpec(
            name="browser_wait_for_response",
            description="Wait until a response matches url_pattern; returns metadata.",
            args_model=BrowserWaitForResponseArgs,
            handler=_browser_wait_for_response,
            defer_loading=True,
        ),  # noqa: E501
        ToolSpec(
            name="browser_get_network_log",
            description="Read the buffered network request log captured by interceptors.",
            args_model=BrowserGetNetworkLogArgs,
            handler=_browser_get_network_log,
            defer_loading=True,
        ),  # noqa: E501
    ]
