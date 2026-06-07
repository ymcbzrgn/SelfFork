"""Browser observation tools — screenshot/dom/text/attribute/eval/query/pdf/element/html/logs."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.browser._internal import (
    _invoke_browser,
    _require_browser_driver,
)

__all__ = [
    "BrowserDomSnapshotArgs",
    "BrowserEvaluateArgs",
    "BrowserGetAttributeArgs",
    "BrowserGetConsoleLogsArgs",
    "BrowserGetHtmlArgs",
    "BrowserGetPdfArgs",
    "BrowserQuerySelectorAllArgs",
    "BrowserQuerySelectorArgs",
    "BrowserScreenshotArgs",
    "BrowserScreenshotElementArgs",
    "BrowserTextContentArgs",
    "build_browser_observation_tools",
]


class BrowserScreenshotArgs(ToolArgs):
    rect: tuple[int, int, int, int] | None = Field(default=None, description="x,y,w,h clip")


class BrowserDomSnapshotArgs(ToolArgs):
    pass


class BrowserTextContentArgs(ToolArgs):
    target: str = Field(min_length=1, max_length=1024)


class BrowserGetAttributeArgs(ToolArgs):
    target: str = Field(min_length=1, max_length=1024)
    name: str = Field(min_length=1, max_length=128)


class BrowserEvaluateArgs(ToolArgs):
    js_code: str = Field(min_length=1, max_length=8_192)


class BrowserQuerySelectorArgs(ToolArgs):
    target: str = Field(min_length=1, max_length=1024)


class BrowserQuerySelectorAllArgs(ToolArgs):
    target: str = Field(min_length=1, max_length=1024)
    max_items: int = Field(default=100, ge=1, le=10_000)


class BrowserGetPdfArgs(ToolArgs):
    output_path: str | None = Field(default=None, max_length=4096)


class BrowserScreenshotElementArgs(ToolArgs):
    target: str = Field(min_length=1, max_length=1024)


class BrowserGetHtmlArgs(ToolArgs):
    pass


class BrowserGetConsoleLogsArgs(ToolArgs):
    pass


async def _browser_screenshot(ctx: ToolContext, args: BrowserScreenshotArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _shot() -> dict[str, Any]:
        png = await drv.screenshot(args.rect)
        ref = None
        store: Any = ctx.screenshot_store
        if store is not None:
            try:
                ref_obj = store.write(
                    png,
                    session_id=ctx.session_id,
                    project_slug=ctx.project_slug,
                )
                ref = {
                    "path": str(ref_obj.path),
                    "sha256": ref_obj.sha256,
                    "bytes_size": ref_obj.bytes_size,
                }  # noqa: E501
            except Exception:
                ref = None
        return {"bytes_size": len(png), "ref": ref}

    return await _invoke_browser(
        ctx,
        action_type="browser.screenshot",
        target_uri=None,
        args_summary={"rect": args.rect},
        coro_factory=_shot,
    )


async def _browser_dom_snapshot(
    ctx: ToolContext,
    args: BrowserDomSnapshotArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _dump() -> dict[str, Any]:
        tree = await drv.dump_dom_tree()
        return {"node_count": len(tree), "preview": tree[:50]}

    return await _invoke_browser(
        ctx,
        action_type="browser.dom_snapshot",
        target_uri=None,
        args_summary={},
        coro_factory=_dump,
    )


async def _browser_text_content(
    ctx: ToolContext,
    args: BrowserTextContentArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _read() -> dict[str, Any]:
        text = await drv.text_content(args.target)
        return {"text": text[:16_384], "len": len(text)}

    return await _invoke_browser(
        ctx,
        action_type="browser.text_content",
        target_uri=args.target,
        args_summary={"target": args.target},
        coro_factory=_read,
    )


async def _browser_get_attribute(
    ctx: ToolContext,
    args: BrowserGetAttributeArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _read() -> dict[str, Any]:
        value = await drv.get_attribute(args.target, args.name)
        return {"name": args.name, "value": value}

    return await _invoke_browser(
        ctx,
        action_type="browser.get_attribute",
        target_uri=args.target,
        args_summary={"target": args.target, "name": args.name},
        coro_factory=_read,
    )


async def _browser_evaluate(ctx: ToolContext, args: BrowserEvaluateArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _eval() -> dict[str, Any]:
        result = await drv.evaluate(args.js_code)
        return {"result": repr(result)[:8192]}

    return await _invoke_browser(
        ctx,
        action_type="browser.evaluate",
        target_uri=None,
        args_summary={"js_len": len(args.js_code)},
        coro_factory=_eval,
    )


async def _browser_query_selector(
    ctx: ToolContext,
    args: BrowserQuerySelectorArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _q() -> dict[str, Any]:
        el = await drv.query_selector(args.target)
        return {"found": el is not None, "element": el}

    return await _invoke_browser(
        ctx,
        action_type="browser.query_selector",
        target_uri=args.target,
        args_summary={"target": args.target},
        coro_factory=_q,
    )


async def _browser_query_selector_all(
    ctx: ToolContext,
    args: BrowserQuerySelectorAllArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _q() -> dict[str, Any]:
        els = await drv.query_selector_all(args.target, max_items=args.max_items)
        return {"count": len(els), "elements": els}

    return await _invoke_browser(
        ctx,
        action_type="browser.query_selector_all",
        target_uri=args.target,
        args_summary={"target": args.target, "max_items": args.max_items},
        coro_factory=_q,
    )


async def _browser_get_pdf(ctx: ToolContext, args: BrowserGetPdfArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _pdf() -> dict[str, Any]:
        data = await drv.get_pdf(args.output_path)
        return {"bytes_size": len(data), "output_path": args.output_path}

    return await _invoke_browser(
        ctx,
        action_type="browser.get_pdf",
        target_uri=args.output_path,
        args_summary={"output_path": args.output_path},
        coro_factory=_pdf,
    )


async def _browser_screenshot_element(
    ctx: ToolContext,
    args: BrowserScreenshotElementArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _shot() -> dict[str, Any]:
        png = await drv.screenshot_element(args.target)
        return {"bytes_size": len(png)}

    return await _invoke_browser(
        ctx,
        action_type="browser.screenshot_element",
        target_uri=args.target,
        args_summary={"target": args.target},
        coro_factory=_shot,
    )


async def _browser_get_html(ctx: ToolContext, args: BrowserGetHtmlArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _html() -> dict[str, Any]:
        html = await drv.get_html()
        return {"len": len(html), "preview": html[:8192]}

    return await _invoke_browser(
        ctx,
        action_type="browser.get_html",
        target_uri=None,
        args_summary={},
        coro_factory=_html,
    )


async def _browser_get_console_logs(
    ctx: ToolContext,
    args: BrowserGetConsoleLogsArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _logs() -> dict[str, Any]:
        logs = await drv.get_console_logs()
        return {"count": len(logs), "preview": logs[:50]}

    return await _invoke_browser(
        ctx,
        action_type="browser.get_console_logs",
        target_uri=None,
        args_summary={},
        coro_factory=_logs,
    )


def build_browser_observation_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="browser_screenshot",
            description="Capture page screenshot (optional rect clip); persists to ScreenshotStore.",  # noqa: E501
            args_model=BrowserScreenshotArgs,
            handler=_browser_screenshot,
            defer_loading=False,
        ),
        ToolSpec(
            name="browser_dom_snapshot",
            description="Extract the simplified DOM tree (interactive nodes + ARIA roles).",
            args_model=BrowserDomSnapshotArgs,
            handler=_browser_dom_snapshot,
            defer_loading=False,
        ),
        ToolSpec(
            name="browser_text_content",
            description="Read text content of a CSS selector.",
            args_model=BrowserTextContentArgs,
            handler=_browser_text_content,
            defer_loading=False,
        ),
        ToolSpec(
            name="browser_evaluate",
            description="Run an arbitrary JS expression on the page (T2 risk_tier).",
            args_model=BrowserEvaluateArgs,
            handler=_browser_evaluate,
            defer_loading=False,
        ),
        ToolSpec(
            name="browser_get_attribute",
            description="Read an attribute of a CSS-selected element.",
            args_model=BrowserGetAttributeArgs,
            handler=_browser_get_attribute,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_query_selector",
            description="Query the first matching element; returns tag/text/visible.",
            args_model=BrowserQuerySelectorArgs,
            handler=_browser_query_selector,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_query_selector_all",
            description="Query all matching elements (capped by max_items).",
            args_model=BrowserQuerySelectorAllArgs,
            handler=_browser_query_selector_all,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_get_pdf",
            description="Render the page as PDF; optional output_path persists to disk.",
            args_model=BrowserGetPdfArgs,
            handler=_browser_get_pdf,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_screenshot_element",
            description="Screenshot a single element by CSS selector.",
            args_model=BrowserScreenshotElementArgs,
            handler=_browser_screenshot_element,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_get_html",
            description="Read the full rendered HTML source.",
            args_model=BrowserGetHtmlArgs,
            handler=_browser_get_html,
            defer_loading=True,
        ),
        ToolSpec(
            name="browser_get_console_logs",
            description="Read the buffered console.log entries captured since start.",
            args_model=BrowserGetConsoleLogsArgs,
            handler=_browser_get_console_logs,
            defer_loading=True,
        ),
    ]
