"""Desktop handler dispatch tests."""

from __future__ import annotations

import pytest

from selffork_orchestrator.tools.base import _UnauthorizedError
from selffork_orchestrator.tools.desktop._internal import _require_macos_driver
from selffork_orchestrator.tools.desktop.tools import (
    DesktopClickArgs,
    DesktopDoubleClickArgs,
    DesktopFocusWindowArgs,
    DesktopGetActiveAppArgs,
    DesktopGetClipboardArgs,
    DesktopListAppsArgs,
    DesktopListWindowsArgs,
    DesktopNotificationArgs,
    DesktopPressKeyArgs,
    DesktopRightClickArgs,
    DesktopSayArgs,
    DesktopScreenshotArgs,
    DesktopScreenshotRegionArgs,
    DesktopSetClipboardArgs,
    DesktopTypeArgs,
    _desktop_click,
    _desktop_double_click,
    _desktop_focus_window,
    _desktop_get_active_app,
    _desktop_get_clipboard,
    _desktop_list_apps,
    _desktop_list_windows,
    _desktop_notification,
    _desktop_press_key,
    _desktop_right_click,
    _desktop_say,
    _desktop_screenshot,
    _desktop_screenshot_region,
    _desktop_set_clipboard,
    _desktop_type,
)


async def test_require_macos_driver(ctx_macos, stub_macos_driver) -> None:
    assert _require_macos_driver(ctx_macos) is stub_macos_driver


async def test_require_macos_driver_no_driver(ctx_no_driver_with_warden) -> None:
    with pytest.raises(_UnauthorizedError):
        _require_macos_driver(ctx_no_driver_with_warden)


async def test_desktop_click(ctx_macos, stub_macos_driver) -> None:
    result = await _desktop_click(ctx_macos, DesktopClickArgs(x=10, y=20))
    assert result["status"] == "ok"
    assert any(c[0] == "click" for c in stub_macos_driver.calls)


async def test_desktop_double_click(ctx_macos, stub_macos_driver) -> None:
    await _desktop_double_click(ctx_macos, DesktopDoubleClickArgs(x=5, y=5))
    assert ("double_click", (5, 5), {}) in stub_macos_driver.calls


async def test_desktop_right_click(ctx_macos, stub_macos_driver) -> None:
    await _desktop_right_click(ctx_macos, DesktopRightClickArgs(x=5, y=5))
    assert ("right_click", (5, 5), {}) in stub_macos_driver.calls


async def test_desktop_type(ctx_macos, stub_macos_driver) -> None:
    await _desktop_type(ctx_macos, DesktopTypeArgs(text="hello"))
    assert any(c[0] == "type_text" for c in stub_macos_driver.calls)


async def test_desktop_press_key(ctx_macos, stub_macos_driver) -> None:
    await _desktop_press_key(ctx_macos, DesktopPressKeyArgs(key_combo="cmd+t"))
    assert ("press_key", ("cmd+t",), {}) in stub_macos_driver.calls


async def test_desktop_screenshot(ctx_macos, stub_macos_driver) -> None:
    result = await _desktop_screenshot(ctx_macos, DesktopScreenshotArgs())
    assert result["result"]["bytes_size"] > 0


async def test_desktop_screenshot_region(ctx_macos, stub_macos_driver) -> None:
    result = await _desktop_screenshot_region(
        ctx_macos,
        DesktopScreenshotRegionArgs(x=0, y=0, width=100, height=100),
    )
    assert result["result"]["bytes_size"] > 0


async def test_desktop_get_active_app(ctx_macos, stub_macos_driver) -> None:
    result = await _desktop_get_active_app(ctx_macos, DesktopGetActiveAppArgs())
    assert result["result"]["app"]["name"] == "Terminal"


async def test_desktop_list_apps(ctx_macos, stub_macos_driver) -> None:
    result = await _desktop_list_apps(ctx_macos, DesktopListAppsArgs())
    assert result["result"]["count"] == 1


async def test_desktop_list_windows(ctx_macos, stub_macos_driver) -> None:
    result = await _desktop_list_windows(
        ctx_macos,
        DesktopListWindowsArgs(app_name="Terminal"),
    )
    assert result["result"]["count"] == 1


async def test_desktop_focus_window(ctx_macos, stub_macos_driver) -> None:
    await _desktop_focus_window(
        ctx_macos,
        DesktopFocusWindowArgs(app_name="Terminal", window_title="bash"),
    )
    assert any(c[0] == "focus_window" for c in stub_macos_driver.calls)


async def test_desktop_get_clipboard(ctx_macos, stub_macos_driver) -> None:
    result = await _desktop_get_clipboard(ctx_macos, DesktopGetClipboardArgs())
    assert result["result"]["text"] == "clip"


async def test_desktop_set_clipboard(ctx_macos, stub_macos_driver) -> None:
    await _desktop_set_clipboard(ctx_macos, DesktopSetClipboardArgs(text="hi"))
    assert ("set_clipboard", ("hi",), {}) in stub_macos_driver.calls


async def test_desktop_notification(ctx_macos, stub_macos_driver) -> None:
    await _desktop_notification(
        ctx_macos,
        DesktopNotificationArgs(title="T", body="B"),
    )
    assert ("notification", ("T", "B", None), {}) in stub_macos_driver.calls


async def test_desktop_say(ctx_macos, stub_macos_driver) -> None:
    await _desktop_say(ctx_macos, DesktopSayArgs(text="hello"))
    assert any(c[0] == "say" for c in stub_macos_driver.calls)
