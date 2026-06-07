"""Android handler dispatch tests — each tool reaches the stub driver via _invoke_mobile."""

from __future__ import annotations

import pytest

from selffork_orchestrator.tools.base import _UnauthorizedError
from selffork_orchestrator.tools.mobile._internal import _require_android_driver
from selffork_orchestrator.tools.mobile.android.emulator import (
    AndroidDeviceListArgs,
    AndroidSetGeolocationArgs,
    _android_device_list,
    _android_set_geolocation,
)
from selffork_orchestrator.tools.mobile.android.intent import (
    AndroidBroadcastArgs,
    AndroidDeeplinkArgs,
    AndroidIntentArgs,
    AndroidNotificationPostArgs,
    AndroidPressButtonArgs,
    _android_broadcast,
    _android_deeplink,
    _android_intent,
    _android_notification_post,
    _android_press_button,
)
from selffork_orchestrator.tools.mobile.android.interaction import (
    AndroidClearTextArgs,
    AndroidClickArgs,
    AndroidDoubleClickArgs,
    AndroidLongPressArgs,
    AndroidPinchArgs,
    AndroidPressKeyArgs,
    AndroidScrollArgs,
    AndroidSwipeArgs,
    AndroidTypeArgs,
    _android_clear_text,
    _android_click,
    _android_double_click,
    _android_long_press,
    _android_pinch,
    _android_press_key,
    _android_scroll,
    _android_swipe,
    _android_type,
)
from selffork_orchestrator.tools.mobile.android.lifecycle import (
    AndroidAppActivateArgs,
    AndroidAppClearDataArgs,
    AndroidAppForceStopArgs,
    AndroidAppLaunchArgs,
    AndroidAppTerminateArgs,
    AndroidInstallAppArgs,
    AndroidListAppsArgs,
    AndroidUninstallAppArgs,
    _android_app_activate,
    _android_app_clear_data,
    _android_app_force_stop,
    _android_app_launch,
    _android_app_terminate,
    _android_install_app,
    _android_list_apps,
    _android_uninstall_app,
)
from selffork_orchestrator.tools.mobile.android.observation import (
    AndroidAxTreeArgs,
    AndroidScreenshotArgs,
    AndroidScreenTextArgs,
    _android_ax_tree,
    _android_screen_text,
    _android_screenshot,
)
from selffork_orchestrator.tools.mobile.android.shell import (
    AndroidDumpsysArgs,
    AndroidLogcatArgs,
    AndroidPullArgs,
    AndroidPushArgs,
    AndroidScreenrecordStartArgs,
    AndroidScreenrecordStopArgs,
    AndroidShellArgs,
    _android_dumpsys,
    _android_logcat,
    _android_pull,
    _android_push,
    _android_screenrecord_start,
    _android_screenrecord_stop,
    _android_shell,
)
from selffork_orchestrator.tools.mobile.android.system import (
    AndroidGetBatteryArgs,
    AndroidGetClipboardArgs,
    AndroidGetOrientationArgs,
    AndroidGetPropertyArgs,
    AndroidRebootArgs,
    AndroidSetClipboardArgs,
    AndroidSetOrientationArgs,
    AndroidSetPropertyArgs,
    _android_get_battery,
    _android_get_clipboard,
    _android_get_orientation,
    _android_get_property,
    _android_reboot,
    _android_set_clipboard,
    _android_set_orientation,
    _android_set_property,
)

# ---- _require_android_driver ---------------------------------------------


async def test_require_android_driver_returns_driver(ctx_android, stub_android_driver) -> None:
    drv = _require_android_driver(ctx_android)
    assert drv is stub_android_driver


async def test_require_android_driver_rejects_ios(ctx_ios) -> None:
    with pytest.raises(_UnauthorizedError):
        _require_android_driver(ctx_ios)


async def test_require_android_driver_accepts_composite(
    ctx_composite,
    stub_composite_driver,
) -> None:
    drv = _require_android_driver(ctx_composite)
    assert drv is stub_composite_driver.android


# ---- Interaction ---------------------------------------------------------


async def test_android_click_dispatches(ctx_android, stub_android_driver) -> None:
    # Tools call drv.mcp.tap — add mcp passthrough on stub
    captured: dict[str, tuple] = {}

    class _Mcp:
        async def tap(self, x, y):
            captured["tap"] = (x, y)

    stub_android_driver.mcp = _Mcp()  # type: ignore[attr-defined]
    result = await _android_click(ctx_android, AndroidClickArgs(x=50, y=75))
    assert result["status"] == "ok"
    assert captured["tap"] == (50, 75)


async def test_android_double_click(ctx_android, stub_android_driver) -> None:
    await _android_double_click(ctx_android, AndroidDoubleClickArgs(x=10, y=20))
    assert ("double_click", (10, 20), {}) in stub_android_driver.calls


async def test_android_long_press(ctx_android, stub_android_driver) -> None:
    await _android_long_press(ctx_android, AndroidLongPressArgs(x=5, y=5, duration_ms=900))
    assert ("long_press", (5, 5), {"duration_ms": 900}) in stub_android_driver.calls


async def test_android_type(ctx_android, stub_android_driver) -> None:
    await _android_type(ctx_android, AndroidTypeArgs(text="hello"))
    assert any(c[0] == "type_text" for c in stub_android_driver.calls)


async def test_android_type_with_clear(ctx_android, stub_android_driver) -> None:
    await _android_type(ctx_android, AndroidTypeArgs(text="x", clear_first=True))
    names = [c[0] for c in stub_android_driver.calls]
    assert names.index("clear_text") < names.index("type_text")


async def test_android_clear_text(ctx_android, stub_android_driver) -> None:
    await _android_clear_text(ctx_android, AndroidClearTextArgs())
    assert ("clear_text", (), {}) in stub_android_driver.calls


async def test_android_swipe(ctx_android, stub_android_driver) -> None:
    await _android_swipe(
        ctx_android,
        AndroidSwipeArgs(start_x=0, start_y=0, end_x=10, end_y=20),
    )
    assert any(c[0] == "swipe" for c in stub_android_driver.calls)


async def test_android_scroll(ctx_android, stub_android_driver) -> None:
    await _android_scroll(ctx_android, AndroidScrollArgs(direction="down", amount=500))
    assert ("scroll", (), {"direction": "down", "amount": 500}) in stub_android_driver.calls


async def test_android_press_key(ctx_android, stub_android_driver) -> None:
    await _android_press_key(ctx_android, AndroidPressKeyArgs(key="back"))
    assert ("press_key", ("back",), {}) in stub_android_driver.calls


async def test_android_pinch(ctx_android, stub_android_driver) -> None:
    await _android_pinch(ctx_android, AndroidPinchArgs(scale=0.5))
    assert ("pinch", (0.5,), {"velocity": 1.0}) in stub_android_driver.calls


# ---- Observation ---------------------------------------------------------


async def test_android_screenshot(ctx_android, stub_android_driver) -> None:
    result = await _android_screenshot(ctx_android, AndroidScreenshotArgs())
    assert result["result"]["bytes_size"] > 0


async def test_android_ax_tree(ctx_android, stub_android_driver) -> None:
    result = await _android_ax_tree(ctx_android, AndroidAxTreeArgs())
    assert "tree_chars" in result["result"]


async def test_android_screen_text(ctx_android, stub_android_driver) -> None:
    result = await _android_screen_text(ctx_android, AndroidScreenTextArgs())
    assert "text" in result["result"]


# ---- Lifecycle -----------------------------------------------------------


async def test_android_app_launch(ctx_android, stub_android_driver) -> None:
    await _android_app_launch(ctx_android, AndroidAppLaunchArgs(package="com.x"))
    assert ("app_launch", ("com.x",), {}) in stub_android_driver.calls


async def test_android_app_terminate(ctx_android, stub_android_driver) -> None:
    await _android_app_terminate(ctx_android, AndroidAppTerminateArgs(package="com.x"))
    assert ("app_terminate", ("com.x",), {}) in stub_android_driver.calls


async def test_android_app_force_stop(ctx_android, stub_android_driver) -> None:
    await _android_app_force_stop(ctx_android, AndroidAppForceStopArgs(package="com.x"))
    assert ("app_force_stop", ("com.x",), {}) in stub_android_driver.calls


async def test_android_app_clear_data(ctx_android, stub_android_driver) -> None:
    await _android_app_clear_data(ctx_android, AndroidAppClearDataArgs(package="com.x"))
    assert ("app_clear_data", ("com.x",), {}) in stub_android_driver.calls


async def test_android_install_app(ctx_android, stub_android_driver) -> None:
    await _android_install_app(ctx_android, AndroidInstallAppArgs(apk_path="/tmp/x.apk"))
    assert any(c[0] == "install_app" for c in stub_android_driver.calls)


async def test_android_uninstall_app(ctx_android, stub_android_driver) -> None:
    await _android_uninstall_app(ctx_android, AndroidUninstallAppArgs(package="com.x"))
    assert ("uninstall_app", ("com.x",), {}) in stub_android_driver.calls


async def test_android_list_apps(ctx_android, stub_android_driver) -> None:
    result = await _android_list_apps(ctx_android, AndroidListAppsArgs())
    assert result["result"]["count"] == 1


async def test_android_app_activate(ctx_android, stub_android_driver) -> None:
    await _android_app_activate(ctx_android, AndroidAppActivateArgs(package="com.x"))
    assert ("app_activate", ("com.x",), {}) in stub_android_driver.calls


# ---- System --------------------------------------------------------------


async def test_android_get_orientation(ctx_android, stub_android_driver) -> None:
    result = await _android_get_orientation(ctx_android, AndroidGetOrientationArgs())
    assert "orientation" in result["result"]


async def test_android_set_orientation(ctx_android, stub_android_driver) -> None:
    await _android_set_orientation(
        ctx_android,
        AndroidSetOrientationArgs(orientation="LANDSCAPE"),
    )
    assert ("set_orientation", ("LANDSCAPE",), {}) in stub_android_driver.calls


async def test_android_get_clipboard(ctx_android, stub_android_driver) -> None:
    result = await _android_get_clipboard(ctx_android, AndroidGetClipboardArgs())
    assert result["result"]["text"] == "clip"


async def test_android_set_clipboard(ctx_android, stub_android_driver) -> None:
    await _android_set_clipboard(ctx_android, AndroidSetClipboardArgs(text="x"))
    assert ("set_clipboard", ("x",), {}) in stub_android_driver.calls


async def test_android_get_property(ctx_android, stub_android_driver) -> None:
    result = await _android_get_property(
        ctx_android,
        AndroidGetPropertyArgs(key="ro.build.version.sdk"),
    )
    assert result["result"]["value"] == "value"


async def test_android_set_property(ctx_android, stub_android_driver) -> None:
    await _android_set_property(
        ctx_android,
        AndroidSetPropertyArgs(key="debug.x", value="1"),
    )
    assert ("set_property", ("debug.x", "1"), {}) in stub_android_driver.calls


async def test_android_reboot(ctx_android, stub_android_driver) -> None:
    await _android_reboot(ctx_android, AndroidRebootArgs())
    assert ("reboot", (), {}) in stub_android_driver.calls


async def test_android_get_battery(ctx_android, stub_android_driver) -> None:
    result = await _android_get_battery(ctx_android, AndroidGetBatteryArgs())
    assert "battery" in result["result"]


# ---- Intent --------------------------------------------------------------


async def test_android_intent(ctx_android, stub_android_driver) -> None:
    result = await _android_intent(
        ctx_android,
        AndroidIntentArgs(action="android.intent.action.VIEW", data="https://x"),
    )
    assert result["status"] == "ok"


async def test_android_broadcast(ctx_android, stub_android_driver) -> None:
    result = await _android_broadcast(
        ctx_android,
        AndroidBroadcastArgs(action="X.ACTION"),
    )
    assert result["status"] == "ok"


async def test_android_deeplink(ctx_android, stub_android_driver) -> None:
    result = await _android_deeplink(
        ctx_android,
        AndroidDeeplinkArgs(url="myapp://route"),
    )
    assert result["status"] == "ok"


async def test_android_press_button(ctx_android, stub_android_driver) -> None:
    await _android_press_button(
        ctx_android,
        AndroidPressButtonArgs(button="recent"),
    )
    # Handler delegates to drv.press_button (stub records it under that name);
    # the real AndroidDriver.press_button translates "recent" → "app_switch"
    # and then calls press_key, but the stub records the outer call only.
    assert any(c[0] == "press_button" for c in stub_android_driver.calls)


async def test_android_notification_post(ctx_android, stub_android_driver) -> None:
    result = await _android_notification_post(
        ctx_android,
        AndroidNotificationPostArgs(title="T", body="B"),
    )
    assert result["status"] == "ok"


# ---- Shell ---------------------------------------------------------------


async def test_android_shell(ctx_android, stub_android_driver) -> None:
    result = await _android_shell(ctx_android, AndroidShellArgs(command="ls /"))
    assert result["status"] == "ok"
    assert "output" in result["result"]


async def test_android_pull(ctx_android, stub_android_driver) -> None:
    await _android_pull(
        ctx_android,
        AndroidPullArgs(remote="/sdcard/x", local="/tmp/x"),
    )
    assert any(c[0] == "pull" for c in stub_android_driver.calls)


async def test_android_push(ctx_android, stub_android_driver) -> None:
    await _android_push(
        ctx_android,
        AndroidPushArgs(local="/tmp/x", remote="/sdcard/x"),
    )
    assert any(c[0] == "push" for c in stub_android_driver.calls)


async def test_android_logcat(ctx_android, stub_android_driver) -> None:
    result = await _android_logcat(ctx_android, AndroidLogcatArgs(max_lines=50))
    assert result["status"] == "ok"


async def test_android_dumpsys(ctx_android, stub_android_driver) -> None:
    result = await _android_dumpsys(ctx_android, AndroidDumpsysArgs(service="battery"))
    assert result["status"] == "ok"


async def test_android_screenrecord_start(ctx_android, stub_android_driver) -> None:
    await _android_screenrecord_start(
        ctx_android,
        AndroidScreenrecordStartArgs(output_path="/tmp/v.mp4"),
    )
    assert any(c[0] == "screenrecord_start" for c in stub_android_driver.calls)


async def test_android_screenrecord_stop(ctx_android, stub_android_driver) -> None:
    result = await _android_screenrecord_stop(
        ctx_android,
        AndroidScreenrecordStopArgs(),
    )
    assert result["result"]["output_path"].endswith(".mp4")


# ---- Emulator ------------------------------------------------------------


async def test_android_device_list(ctx_android, stub_android_driver) -> None:
    result = await _android_device_list(ctx_android, AndroidDeviceListArgs())
    assert result["result"]["count"] == 1


async def test_android_set_geolocation(ctx_android, stub_android_driver) -> None:
    await _android_set_geolocation(
        ctx_android,
        AndroidSetGeolocationArgs(latitude=40.0, longitude=-3.7),
    )
    assert any(c[0] == "set_geolocation" for c in stub_android_driver.calls)
