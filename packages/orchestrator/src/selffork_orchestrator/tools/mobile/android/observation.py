"""Android observation tools — screenshot / a11y tree / screen text (3 tools)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_android_driver,
)

__all__ = [
    "AndroidAxTreeArgs",
    "AndroidScreenTextArgs",
    "AndroidScreenshotArgs",
    "build_android_observation_tools",
]


class AndroidScreenshotArgs(ToolArgs):
    pass


class AndroidAxTreeArgs(ToolArgs):
    pass


class AndroidScreenTextArgs(ToolArgs):
    region: tuple[int, int, int, int] | None = Field(default=None)


async def _android_screenshot(
    ctx: ToolContext,
    args: AndroidScreenshotArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

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
        action_type="android.screenshot",
        target_uri=None,
        args_summary={},
        coro_factory=_capture,
    )


async def _android_ax_tree(
    ctx: ToolContext,
    args: AndroidAxTreeArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _dump() -> dict[str, Any]:
        tree = await drv.ax_tree()
        text = str(tree)
        return {"tree_chars": len(text), "preview": text[:4096]}

    return await _invoke_mobile(
        ctx,
        action_type="android.ax_tree",
        target_uri=None,
        args_summary={},
        coro_factory=_dump,
    )


async def _android_screen_text(
    ctx: ToolContext,
    args: AndroidScreenTextArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _extract() -> dict[str, Any]:
        text = await drv.ax_tree()
        return {
            "text": str(text)[:8192],
            "region": list(args.region) if args.region else None,
            "source": "ax_tree",
        }

    return await _invoke_mobile(
        ctx,
        action_type="android.screen_text",
        target_uri=None,
        args_summary={"region": args.region},
        coro_factory=_extract,
    )


def build_android_observation_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="android_screenshot",
            description=(
                "Capture Android screenshot as PNG bytes; persisted to ScreenshotStore when wired."
            ),
            args_model=AndroidScreenshotArgs,
            handler=_android_screenshot,
            defer_loading=False,
        ),
        ToolSpec(
            name="android_a11y_tree",
            description="Dump the Android accessibility tree (mobile-mcp).",
            args_model=AndroidAxTreeArgs,
            handler=_android_ax_tree,
            defer_loading=False,
        ),
        ToolSpec(
            name="android_screen_text",
            description=(
                "Extract visible text from the Android screen via the "
                "a11y tree; optional region filter."
            ),
            args_model=AndroidScreenTextArgs,
            handler=_android_screen_text,
            defer_loading=True,
        ),
    ]
