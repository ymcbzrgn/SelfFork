"""iOS observation tools — screenshot / a11y tree / screen text (3 tools)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_ios_driver,
)

__all__ = [
    "IosAxTreeArgs",
    "IosScreenTextArgs",
    "IosScreenshotArgs",
    "build_ios_observation_tools",
]


class IosScreenshotArgs(ToolArgs):
    pass


class IosAxTreeArgs(ToolArgs):
    pass


class IosScreenTextArgs(ToolArgs):
    region: tuple[int, int, int, int] | None = Field(
        default=None,
        description="Optional (x, y, w, h) region; full screen when omitted",
    )


async def _ios_screenshot(ctx: ToolContext, args: IosScreenshotArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _capture() -> dict[str, Any]:
        png = await drv.screenshot()
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
                }
            except Exception:
                ref = None
        return {"bytes_size": len(png), "ref": ref}

    return await _invoke_mobile(
        ctx,
        action_type="ios.screenshot",
        target_uri=None,
        args_summary={},
        coro_factory=_capture,
    )


async def _ios_ax_tree(ctx: ToolContext, args: IosAxTreeArgs) -> dict[str, Any]:
    drv = _require_ios_driver(ctx)

    async def _dump() -> dict[str, Any]:
        tree = await drv.ax_tree()
        # Trim very long trees to keep tool result under audit cap.
        text = str(tree)
        return {"tree_chars": len(text), "preview": text[:4096]}

    return await _invoke_mobile(
        ctx,
        action_type="ios.ax_tree",
        target_uri=None,
        args_summary={},
        coro_factory=_dump,
    )


async def _ios_screen_text(ctx: ToolContext, args: IosScreenTextArgs) -> dict[str, Any]:
    """Capture screenshot + run OCR-like extraction; ax_tree first, OCR fallback.

    For Faz 1 we lean on the a11y tree (Appium ``page_source``) which
    already exposes labelled text without an OCR dep. The ``region``
    arg is recorded in the audit but applied client-side by the
    consumer — full-screen text in the response.
    """
    drv = _require_ios_driver(ctx)

    async def _extract() -> dict[str, Any]:
        text = await drv.ax_tree()
        return {
            "text": str(text)[:8192],
            "region": list(args.region) if args.region else None,
            "source": "ax_tree",
        }

    return await _invoke_mobile(
        ctx,
        action_type="ios.screen_text",
        target_uri=None,
        args_summary={"region": args.region},
        coro_factory=_extract,
    )


def build_ios_observation_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="ios_screenshot",
            description=(
                "Capture iOS simulator screenshot as PNG bytes; persisted "
                "to ScreenshotStore when wired."
            ),
            args_model=IosScreenshotArgs,
            handler=_ios_screenshot,
            defer_loading=False,
        ),
        ToolSpec(
            name="ios_a11y_tree",
            description="Dump the iOS accessibility tree (Appium page_source).",
            args_model=IosAxTreeArgs,
            handler=_ios_ax_tree,
            defer_loading=False,
        ),
        ToolSpec(
            name="ios_screen_text",
            description=(
                "Extract visible text from the iOS screen via the a11y "
                "tree; optional region filter."
            ),
            args_model=IosScreenTextArgs,
            handler=_ios_screen_text,
            defer_loading=True,
        ),
    ]
