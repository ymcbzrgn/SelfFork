"""Desktop tools — click/type/screenshot/clipboard/notification/say (15 tools)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.desktop._internal import (
    _invoke_desktop,
    _require_macos_driver,
)

__all__ = [
    "DesktopClickArgs",
    "DesktopDoubleClickArgs",
    "DesktopFocusWindowArgs",
    "DesktopGetActiveAppArgs",
    "DesktopGetClipboardArgs",
    "DesktopListAppsArgs",
    "DesktopListWindowsArgs",
    "DesktopNotificationArgs",
    "DesktopPressKeyArgs",
    "DesktopRightClickArgs",
    "DesktopSayArgs",
    "DesktopScreenshotArgs",
    "DesktopScreenshotRegionArgs",
    "DesktopSetClipboardArgs",
    "DesktopTypeArgs",
    "build_desktop_tools_inner",
]


class DesktopClickArgs(ToolArgs):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class DesktopDoubleClickArgs(ToolArgs):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class DesktopRightClickArgs(ToolArgs):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class DesktopTypeArgs(ToolArgs):
    text: str = Field(min_length=1, max_length=10_000)


class DesktopPressKeyArgs(ToolArgs):
    key_combo: str = Field(
        min_length=1,
        max_length=128,
        description="e.g. 'cmd+t', 'enter', 'cmd+shift+4'",
    )


class DesktopScreenshotArgs(ToolArgs):
    pass


class DesktopScreenshotRegionArgs(ToolArgs):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=1, le=20_000)
    height: int = Field(ge=1, le=20_000)


class DesktopGetActiveAppArgs(ToolArgs):
    pass


class DesktopListAppsArgs(ToolArgs):
    pass


class DesktopListWindowsArgs(ToolArgs):
    app_name: str | None = Field(default=None, max_length=128)


class DesktopFocusWindowArgs(ToolArgs):
    app_name: str = Field(min_length=1, max_length=128)
    window_title: str | None = Field(default=None, max_length=512)


class DesktopGetClipboardArgs(ToolArgs):
    pass


class DesktopSetClipboardArgs(ToolArgs):
    text: str = Field(max_length=100_000)


class DesktopNotificationArgs(ToolArgs):
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=1024)
    subtitle: str | None = Field(default=None, max_length=256)


class DesktopSayArgs(ToolArgs):
    text: str = Field(min_length=1, max_length=10_000)
    voice: str | None = Field(default=None, max_length=64)
    rate: int | None = Field(default=None, ge=10, le=720)


async def _desktop_click(ctx: ToolContext, args: DesktopClickArgs) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)
    return await _invoke_desktop(
        ctx,
        action_type="desktop.click",
        target_uri=f"coords:{args.x},{args.y}",
        args_summary={"x": args.x, "y": args.y},
        coro_factory=lambda: drv.click("", bbox=(args.x, args.y, 1, 1)),
    )


async def _desktop_double_click(ctx: ToolContext, args: DesktopDoubleClickArgs) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)
    return await _invoke_desktop(
        ctx,
        action_type="desktop.double_click",
        target_uri=f"coords:{args.x},{args.y}",
        args_summary={"x": args.x, "y": args.y},
        coro_factory=lambda: drv.double_click(args.x, args.y),
    )


async def _desktop_right_click(ctx: ToolContext, args: DesktopRightClickArgs) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)
    return await _invoke_desktop(
        ctx,
        action_type="desktop.right_click",
        target_uri=f"coords:{args.x},{args.y}",
        args_summary={"x": args.x, "y": args.y},
        coro_factory=lambda: drv.right_click(args.x, args.y),
    )


async def _desktop_type(ctx: ToolContext, args: DesktopTypeArgs) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)
    return await _invoke_desktop(
        ctx,
        action_type="desktop.type",
        target_uri=None,
        args_summary={"text_len": len(args.text)},
        coro_factory=lambda: drv.type_text(args.text),
    )


async def _desktop_press_key(ctx: ToolContext, args: DesktopPressKeyArgs) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)
    return await _invoke_desktop(
        ctx,
        action_type="desktop.press_key",
        target_uri=None,
        args_summary={"key_combo": args.key_combo},
        coro_factory=lambda: drv.press_key(args.key_combo),
    )


async def _desktop_screenshot(ctx: ToolContext, args: DesktopScreenshotArgs) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)

    async def _shot() -> dict[str, Any]:
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

    return await _invoke_desktop(
        ctx,
        action_type="desktop.screenshot",
        target_uri=None,
        args_summary={},
        coro_factory=_shot,
    )


async def _desktop_screenshot_region(
    ctx: ToolContext,
    args: DesktopScreenshotRegionArgs,
) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)

    async def _shot() -> dict[str, Any]:
        png = await drv.screenshot_region(args.x, args.y, args.width, args.height)
        return {"bytes_size": len(png)}

    return await _invoke_desktop(
        ctx,
        action_type="desktop.screenshot_region",
        target_uri=None,
        args_summary={
            "x": args.x,
            "y": args.y,
            "width": args.width,
            "height": args.height,
        },
        coro_factory=_shot,
    )


async def _desktop_get_active_app(
    ctx: ToolContext,
    args: DesktopGetActiveAppArgs,
) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)

    async def _get() -> dict[str, Any]:
        info = await drv.get_active_app()
        return {"app": info}

    return await _invoke_desktop(
        ctx,
        action_type="desktop.get_active_app",
        target_uri=None,
        args_summary={},
        coro_factory=_get,
    )


async def _desktop_list_apps(ctx: ToolContext, args: DesktopListAppsArgs) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)

    async def _list() -> dict[str, Any]:
        apps = await drv.list_apps()
        return {"count": len(apps), "apps": apps[:200]}

    return await _invoke_desktop(
        ctx,
        action_type="desktop.list_apps",
        target_uri=None,
        args_summary={},
        coro_factory=_list,
    )


async def _desktop_list_windows(
    ctx: ToolContext,
    args: DesktopListWindowsArgs,
) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)

    async def _list() -> dict[str, Any]:
        wins = await drv.list_windows(args.app_name)
        return {"count": len(wins), "windows": wins[:200]}

    return await _invoke_desktop(
        ctx,
        action_type="desktop.list_windows",
        target_uri=args.app_name,
        args_summary={"app_name": args.app_name},
        coro_factory=_list,
    )


async def _desktop_focus_window(
    ctx: ToolContext,
    args: DesktopFocusWindowArgs,
) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)
    return await _invoke_desktop(
        ctx,
        action_type="desktop.focus_window",
        target_uri=args.app_name,
        args_summary={"app_name": args.app_name, "window_title": args.window_title},
        coro_factory=lambda: drv.focus_window(args.app_name, args.window_title),
    )


async def _desktop_get_clipboard(
    ctx: ToolContext,
    args: DesktopGetClipboardArgs,
) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)

    async def _get() -> dict[str, Any]:
        text = await drv.get_clipboard()
        return {"text": text, "len": len(text)}

    return await _invoke_desktop(
        ctx,
        action_type="desktop.get_clipboard",
        target_uri=None,
        args_summary={},
        coro_factory=_get,
    )


async def _desktop_set_clipboard(
    ctx: ToolContext,
    args: DesktopSetClipboardArgs,
) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)
    return await _invoke_desktop(
        ctx,
        action_type="desktop.set_clipboard",
        target_uri=None,
        args_summary={"text_len": len(args.text)},
        coro_factory=lambda: drv.set_clipboard(args.text),
    )


async def _desktop_notification(
    ctx: ToolContext,
    args: DesktopNotificationArgs,
) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)
    return await _invoke_desktop(
        ctx,
        action_type="desktop.notification",
        target_uri=None,
        args_summary={
            "title_len": len(args.title),
            "body_len": len(args.body),
            "has_subtitle": args.subtitle is not None,
        },
        coro_factory=lambda: drv.notification(args.title, args.body, args.subtitle),
    )


async def _desktop_say(ctx: ToolContext, args: DesktopSayArgs) -> dict[str, Any]:
    drv = _require_macos_driver(ctx)
    return await _invoke_desktop(
        ctx,
        action_type="desktop.say",
        target_uri=None,
        args_summary={
            "text_len": len(args.text),
            "voice": args.voice,
            "rate": args.rate,
        },
        coro_factory=lambda: drv.say(args.text, voice=args.voice, rate=args.rate),
    )


def build_desktop_tools_inner() -> list[ToolSpec[Any]]:
    return [
        # Eager (5) — desktop observe→act loop core
        ToolSpec(
            name="desktop_click",
            description="Click at pixel (x, y) on the macOS desktop.",
            args_model=DesktopClickArgs,
            handler=_desktop_click,
            defer_loading=False,
        ),
        ToolSpec(
            name="desktop_type",
            description="Type text on the active macOS focus.",
            args_model=DesktopTypeArgs,
            handler=_desktop_type,
            defer_loading=False,
        ),
        ToolSpec(
            name="desktop_screenshot",
            description=(
                "Capture full-screen macOS screenshot; persists to ScreenshotStore when wired."
            ),
            args_model=DesktopScreenshotArgs,
            handler=_desktop_screenshot,
            defer_loading=False,
        ),
        ToolSpec(
            name="desktop_press_key",
            description=("Press a key combo on macOS (e.g. 'cmd+t', 'enter', 'cmd+shift+4')."),
            args_model=DesktopPressKeyArgs,
            handler=_desktop_press_key,
            defer_loading=False,
        ),
        ToolSpec(
            name="desktop_get_active_app",
            description="Read the frontmost macOS app (name + bundle ID).",
            args_model=DesktopGetActiveAppArgs,
            handler=_desktop_get_active_app,
            defer_loading=False,
        ),
        # Deferred (10)
        ToolSpec(
            name="desktop_double_click",
            description="Double-click at pixel (x, y).",
            args_model=DesktopDoubleClickArgs,
            handler=_desktop_double_click,
            defer_loading=True,
        ),
        ToolSpec(
            name="desktop_right_click",
            description="Right-click (context menu) at pixel (x, y).",
            args_model=DesktopRightClickArgs,
            handler=_desktop_right_click,
            defer_loading=True,
        ),
        ToolSpec(
            name="desktop_screenshot_region",
            description="Capture a screen rect (x, y, w, h) as PNG bytes.",
            args_model=DesktopScreenshotRegionArgs,
            handler=_desktop_screenshot_region,
            defer_loading=True,
        ),
        ToolSpec(
            name="desktop_list_apps",
            description="List all running (non-background) macOS apps with bundle IDs.",
            args_model=DesktopListAppsArgs,
            handler=_desktop_list_apps,
            defer_loading=True,
        ),
        ToolSpec(
            name="desktop_list_windows",
            description="List windows of the active app (or a specified app by name).",
            args_model=DesktopListWindowsArgs,
            handler=_desktop_list_windows,
            defer_loading=True,
        ),
        ToolSpec(
            name="desktop_focus_window",
            description="Focus a specific app window (cua-style AXRaise; no modal steal).",
            args_model=DesktopFocusWindowArgs,
            handler=_desktop_focus_window,
            defer_loading=True,
        ),
        ToolSpec(
            name="desktop_get_clipboard",
            description="Read the macOS clipboard (pbpaste).",
            args_model=DesktopGetClipboardArgs,
            handler=_desktop_get_clipboard,
            defer_loading=True,
        ),
        ToolSpec(
            name="desktop_set_clipboard",
            description="Write the macOS clipboard (pbcopy).",
            args_model=DesktopSetClipboardArgs,
            handler=_desktop_set_clipboard,
            defer_loading=True,
        ),
        ToolSpec(
            name="desktop_notification",
            description=("Display a macOS notification with title + body (+optional subtitle)."),
            args_model=DesktopNotificationArgs,
            handler=_desktop_notification,
            defer_loading=True,
        ),
        ToolSpec(
            name="desktop_say",
            description=("Speak text via macOS `say` (optional voice / rate)."),
            args_model=DesktopSayArgs,
            handler=_desktop_say,
            defer_loading=True,
        ),
    ]
