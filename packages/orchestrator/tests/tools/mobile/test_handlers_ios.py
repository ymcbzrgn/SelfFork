"""iOS handler dispatch tests — every tool reaches the stub driver via _invoke_mobile."""

from __future__ import annotations

import pytest

from selffork_orchestrator.tools.mobile._internal import _require_ios_driver
from selffork_orchestrator.tools.mobile.ios.element import (
    IosFindElementArgs,
    IosGetActiveElementArgs,
    _ios_find_element,
    _ios_get_active_element,
)
from selffork_orchestrator.tools.mobile.ios.interaction import (
    IosClearTextArgs,
    IosClickArgs,
    IosDoubleClickArgs,
    IosLongPressArgs,
    IosPinchArgs,
    IosPressKeyArgs,
    IosScrollArgs,
    IosSwipeArgs,
    IosTypeArgs,
    _ios_clear_text,
    _ios_click,
    _ios_double_click,
    _ios_long_press,
    _ios_pinch,
    _ios_press_key,
    _ios_scroll,
    _ios_swipe,
    _ios_type,
)
from selffork_orchestrator.tools.mobile.ios.lifecycle import (
    IosAppActivateArgs,
    IosAppBackgroundArgs,
    IosAppLaunchArgs,
    IosAppStateArgs,
    IosAppTerminateArgs,
    IosInstallAppArgs,
    IosListAppsArgs,
    IosUninstallAppArgs,
    _ios_app_activate,
    _ios_app_background,
    _ios_app_launch,
    _ios_app_state,
    _ios_app_terminate,
    _ios_install_app,
    _ios_list_apps,
    _ios_uninstall_app,
)
from selffork_orchestrator.tools.mobile.ios.network import (
    IosGetGeolocationArgs,
    IosOpenUrlArgs,
    IosRecordVideoStartArgs,
    IosRecordVideoStopArgs,
    IosSetGeolocationArgs,
    _ios_get_geolocation,
    _ios_open_url,
    _ios_record_video_start,
    _ios_record_video_stop,
    _ios_set_geolocation,
)
from selffork_orchestrator.tools.mobile.ios.observation import (
    IosAxTreeArgs,
    IosScreenshotArgs,
    IosScreenTextArgs,
    _ios_ax_tree,
    _ios_screen_text,
    _ios_screenshot,
)
from selffork_orchestrator.tools.mobile.ios.simulator import (
    IosBiometricMatchArgs,
    IosBiometricNoMatchArgs,
    IosGetLogsArgs,
    IosSendPushNotificationArgs,
    IosSetAppearanceArgs,
    IosSimulatorBootArgs,
    IosSimulatorEraseArgs,
    IosSimulatorListArgs,
    IosSimulatorShutdownArgs,
    IosStatusBarOverrideArgs,
    _ios_biometric_match,
    _ios_biometric_no_match,
    _ios_get_logs,
    _ios_send_push_notification,
    _ios_set_appearance,
    _ios_simulator_boot,
    _ios_simulator_erase,
    _ios_simulator_list,
    _ios_simulator_shutdown,
    _ios_status_bar_override,
)
from selffork_orchestrator.tools.mobile.ios.system import (
    IosGetClipboardArgs,
    IosGetOrientationArgs,
    IosLockDeviceArgs,
    IosPressButtonArgs,
    IosSetClipboardArgs,
    IosSetOrientationArgs,
    IosTerminateKeyboardArgs,
    IosUnlockDeviceArgs,
    _ios_get_clipboard,
    _ios_get_orientation,
    _ios_lock_device,
    _ios_press_button,
    _ios_set_clipboard,
    _ios_set_orientation,
    _ios_terminate_keyboard,
    _ios_unlock_device,
)

# ---- _require_ios_driver -------------------------------------------------


async def test_require_ios_driver_returns_driver(ctx_ios, stub_ios_driver) -> None:
    drv = _require_ios_driver(ctx_ios)
    assert drv is stub_ios_driver


async def test_require_ios_driver_unauthorized_when_no_driver(ctx_no_driver) -> None:
    from selffork_orchestrator.tools.base import _UnauthorizedError

    with pytest.raises(_UnauthorizedError):
        _require_ios_driver(ctx_no_driver)


async def test_require_ios_driver_rejects_android(ctx_android) -> None:
    from selffork_orchestrator.tools.base import _UnauthorizedError

    with pytest.raises(_UnauthorizedError):
        _require_ios_driver(ctx_android)


async def test_require_ios_driver_accepts_composite_ios(
    ctx_composite, stub_composite_driver,
) -> None:
    drv = _require_ios_driver(ctx_composite)
    assert drv is stub_composite_driver.ios


# ---- Interaction (also exercises _invoke_mobile gate + audit shape) ------


async def test_ios_click_dispatches(ctx_ios, stub_ios_driver) -> None:
    # The interaction handler calls into ``drv._ready_appium().tap`` which
    # the stub doesn't have. We simulate by adding a passthrough method
    # on the stub for this one test.
    captured: dict[str, tuple] = {}

    class _Appium:
        async def tap(self, x, y):
            captured["tap"] = (x, y)

    stub_ios_driver._ready_appium = lambda: _Appium()  # type: ignore[method-assign]
    result = await _ios_click(ctx_ios, IosClickArgs(x=100, y=200))
    assert result["status"] == "ok"
    assert captured["tap"] == (100, 200)


async def test_ios_double_click_dispatches(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_double_click(ctx_ios, IosDoubleClickArgs(x=10, y=20))
    assert result["status"] == "ok"
    assert ("double_click", (10, 20), {}) in stub_ios_driver.calls


async def test_ios_long_press_dispatches(ctx_ios, stub_ios_driver) -> None:
    await _ios_long_press(ctx_ios, IosLongPressArgs(x=5, y=15, duration_ms=1200))
    assert ("long_press", (5, 15), {"duration_ms": 1200}) in stub_ios_driver.calls


async def test_ios_type_no_clear(ctx_ios, stub_ios_driver) -> None:
    await _ios_type(ctx_ios, IosTypeArgs(text="hello"))
    assert any(c[0] == "type_text" for c in stub_ios_driver.calls)
    assert not any(c[0] == "clear_text" for c in stub_ios_driver.calls)


async def test_ios_type_with_clear(ctx_ios, stub_ios_driver) -> None:
    await _ios_type(ctx_ios, IosTypeArgs(text="hello", clear_first=True))
    names = [c[0] for c in stub_ios_driver.calls]
    assert names.index("clear_text") < names.index("type_text")


async def test_ios_clear_text(ctx_ios, stub_ios_driver) -> None:
    await _ios_clear_text(ctx_ios, IosClearTextArgs())
    assert ("clear_text", (), {}) in stub_ios_driver.calls


async def test_ios_swipe(ctx_ios, stub_ios_driver) -> None:
    await _ios_swipe(ctx_ios, IosSwipeArgs(start_x=0, start_y=0, end_x=100, end_y=200))
    assert any(c[0] == "swipe" for c in stub_ios_driver.calls)


async def test_ios_scroll(ctx_ios, stub_ios_driver) -> None:
    await _ios_scroll(ctx_ios, IosScrollArgs(direction="up", amount=400))
    assert ("scroll", (), {"direction": "up", "amount": 400}) in stub_ios_driver.calls


async def test_ios_press_key(ctx_ios, stub_ios_driver) -> None:
    await _ios_press_key(ctx_ios, IosPressKeyArgs(key="home"))
    assert ("press_key", ("home",), {}) in stub_ios_driver.calls


async def test_ios_pinch(ctx_ios, stub_ios_driver) -> None:
    await _ios_pinch(ctx_ios, IosPinchArgs(scale=2.0))
    assert ("pinch", (2.0,), {"velocity": 1.0}) in stub_ios_driver.calls


# ---- Observation ---------------------------------------------------------


async def test_ios_screenshot_returns_bytes_size(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_screenshot(ctx_ios, IosScreenshotArgs())
    assert result["status"] == "ok"
    assert result["result"]["bytes_size"] > 0


async def test_ios_screenshot_persists_when_store_wired(stub_ios_driver, tmp_path) -> None:
    from selffork_body.sandbox import PermissionWarden, WardenMode
    from selffork_body.storage.screenshots import ScreenshotStore
    from selffork_orchestrator.tools.base import ToolContext

    class _StubProjectStore:
        pass

    store = ScreenshotStore(root=tmp_path)
    ctx = ToolContext(
        session_id="sess-test",
        project_slug=None,
        project_store=_StubProjectStore(),
        body_driver=stub_ios_driver,
        permission_warden=PermissionWarden(mode=WardenMode.DANGER_FULL_ACCESS),
        screenshot_store=store,
    )
    result = await _ios_screenshot(ctx, IosScreenshotArgs())
    assert result["result"]["ref"] is not None
    assert result["result"]["ref"]["bytes_size"] > 0


async def test_ios_ax_tree(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_ax_tree(ctx_ios, IosAxTreeArgs())
    assert result["status"] == "ok"
    assert "tree_chars" in result["result"]


async def test_ios_screen_text(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_screen_text(ctx_ios, IosScreenTextArgs())
    assert "text" in result["result"]


# ---- Lifecycle -----------------------------------------------------------


async def test_ios_app_launch(ctx_ios, stub_ios_driver) -> None:
    await _ios_app_launch(ctx_ios, IosAppLaunchArgs(bundle_id="com.x"))
    assert ("app_launch", ("com.x",), {}) in stub_ios_driver.calls


async def test_ios_app_terminate(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_app_terminate(ctx_ios, IosAppTerminateArgs(bundle_id="com.x"))
    assert result["status"] == "ok"


async def test_ios_app_activate(ctx_ios, stub_ios_driver) -> None:
    await _ios_app_activate(ctx_ios, IosAppActivateArgs(bundle_id="com.x"))
    assert ("app_activate", ("com.x",), {}) in stub_ios_driver.calls


async def test_ios_app_state(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_app_state(ctx_ios, IosAppStateArgs(bundle_id="com.x"))
    assert result["status"] == "ok"


async def test_ios_install_app(ctx_ios, stub_ios_driver) -> None:
    await _ios_install_app(ctx_ios, IosInstallAppArgs(app_path="/tmp/x.app"))
    assert any(c[0] == "install_app" for c in stub_ios_driver.calls)


async def test_ios_uninstall_app(ctx_ios, stub_ios_driver) -> None:
    await _ios_uninstall_app(ctx_ios, IosUninstallAppArgs(bundle_id="com.x"))
    assert ("uninstall_app", ("com.x",), {}) in stub_ios_driver.calls


async def test_ios_app_background(ctx_ios, stub_ios_driver) -> None:
    await _ios_app_background(ctx_ios, IosAppBackgroundArgs(seconds=5))
    assert ("app_background", (), {"seconds": 5}) in stub_ios_driver.calls


async def test_ios_list_apps(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_list_apps(ctx_ios, IosListAppsArgs())
    assert result["result"]["count"] == 1


# ---- System --------------------------------------------------------------


async def test_ios_get_orientation(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_get_orientation(ctx_ios, IosGetOrientationArgs())
    assert result["result"]["orientation"] == "PORTRAIT"


async def test_ios_set_orientation(ctx_ios, stub_ios_driver) -> None:
    await _ios_set_orientation(ctx_ios, IosSetOrientationArgs(orientation="LANDSCAPE"))
    assert ("set_orientation", ("LANDSCAPE",), {}) in stub_ios_driver.calls


async def test_ios_get_clipboard(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_get_clipboard(ctx_ios, IosGetClipboardArgs())
    assert result["result"]["text"] == "clip"


async def test_ios_set_clipboard(ctx_ios, stub_ios_driver) -> None:
    await _ios_set_clipboard(ctx_ios, IosSetClipboardArgs(text="hello"))
    assert ("set_clipboard", ("hello",), {}) in stub_ios_driver.calls


async def test_ios_terminate_keyboard(ctx_ios, stub_ios_driver) -> None:
    await _ios_terminate_keyboard(ctx_ios, IosTerminateKeyboardArgs())
    assert ("terminate_keyboard", (), {}) in stub_ios_driver.calls


async def test_ios_lock_device(ctx_ios, stub_ios_driver) -> None:
    await _ios_lock_device(ctx_ios, IosLockDeviceArgs())
    assert ("press_button", ("lock",), {}) in stub_ios_driver.calls


async def test_ios_unlock_device(ctx_ios, stub_ios_driver) -> None:
    await _ios_unlock_device(ctx_ios, IosUnlockDeviceArgs())
    assert ("press_button", ("lock",), {}) in stub_ios_driver.calls


async def test_ios_press_button(ctx_ios, stub_ios_driver) -> None:
    await _ios_press_button(ctx_ios, IosPressButtonArgs(button="volumeup"))
    assert ("press_button", ("volumeup",), {}) in stub_ios_driver.calls


# ---- Simulator -----------------------------------------------------------


async def test_ios_simulator_list(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_simulator_list(ctx_ios, IosSimulatorListArgs())
    assert result["result"]["count"] == 1


async def test_ios_simulator_boot(ctx_ios, stub_ios_driver) -> None:
    udid = "A" * 36
    result = await _ios_simulator_boot(ctx_ios, IosSimulatorBootArgs(udid=udid))
    assert result["result"]["udid"] == udid


async def test_ios_simulator_shutdown(ctx_ios, stub_ios_driver) -> None:
    udid = "A" * 36
    await _ios_simulator_shutdown(ctx_ios, IosSimulatorShutdownArgs(udid=udid))
    assert ("simulator_shutdown", (udid,), {}) in stub_ios_driver.calls


async def test_ios_simulator_erase(ctx_ios, stub_ios_driver) -> None:
    udid = "A" * 36
    await _ios_simulator_erase(ctx_ios, IosSimulatorEraseArgs(udid=udid))
    assert ("simulator_erase", (udid,), {}) in stub_ios_driver.calls


async def test_ios_biometric_match(ctx_ios, stub_ios_driver) -> None:
    await _ios_biometric_match(ctx_ios, IosBiometricMatchArgs())
    assert ("biometric_match", (), {}) in stub_ios_driver.calls


async def test_ios_biometric_no_match(ctx_ios, stub_ios_driver) -> None:
    await _ios_biometric_no_match(ctx_ios, IosBiometricNoMatchArgs())
    assert ("biometric_no_match", (), {}) in stub_ios_driver.calls


async def test_ios_get_logs(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_get_logs(ctx_ios, IosGetLogsArgs())
    assert result["result"]["text_len"] > 0


async def test_ios_send_push_notification(ctx_ios, stub_ios_driver) -> None:
    await _ios_send_push_notification(
        ctx_ios,
        IosSendPushNotificationArgs(payload_path="/tmp/p.json", bundle_id="com.x"),
    )
    assert any(c[0] == "send_push_notification" for c in stub_ios_driver.calls)


async def test_ios_status_bar_override(ctx_ios, stub_ios_driver) -> None:
    await _ios_status_bar_override(
        ctx_ios,
        IosStatusBarOverrideArgs(time="9:41", wifi_bars=3),
    )
    assert any(c[0] == "status_bar_override" for c in stub_ios_driver.calls)


async def test_ios_set_appearance(ctx_ios, stub_ios_driver) -> None:
    await _ios_set_appearance(ctx_ios, IosSetAppearanceArgs(appearance="dark"))
    assert ("set_appearance", ("dark",), {}) in stub_ios_driver.calls


# ---- Network -------------------------------------------------------------


async def test_ios_open_url(ctx_ios, stub_ios_driver) -> None:
    await _ios_open_url(ctx_ios, IosOpenUrlArgs(url="https://example.com"))
    assert ("open_url", ("https://example.com",), {}) in stub_ios_driver.calls


async def test_ios_set_geolocation(ctx_ios, stub_ios_driver) -> None:
    await _ios_set_geolocation(
        ctx_ios, IosSetGeolocationArgs(latitude=40.0, longitude=-3.7),
    )
    assert any(c[0] == "set_geolocation" for c in stub_ios_driver.calls)


async def test_ios_get_geolocation(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_get_geolocation(ctx_ios, IosGetGeolocationArgs())
    assert result["result"]["latitude"] == 1.0


async def test_ios_record_video_start(ctx_ios, stub_ios_driver) -> None:
    await _ios_record_video_start(
        ctx_ios, IosRecordVideoStartArgs(output_path="/tmp/v.mp4"),
    )
    assert any(c[0] == "record_video_start" for c in stub_ios_driver.calls)


async def test_ios_record_video_stop(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_record_video_stop(ctx_ios, IosRecordVideoStopArgs())
    assert result["result"]["output_path"].endswith(".mp4")


# ---- Element queries -----------------------------------------------------


async def test_ios_find_element(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_find_element(
        ctx_ios, IosFindElementArgs(by="accessibility id", value="submit"),
    )
    assert result["status"] == "ok"


async def test_ios_get_active_element(ctx_ios, stub_ios_driver) -> None:
    result = await _ios_get_active_element(ctx_ios, IosGetActiveElementArgs())
    assert result["status"] == "ok"


# ---- Unauthorized when no driver ----------------------------------------


async def test_ios_click_unauthorized_when_no_driver(ctx_no_driver) -> None:
    # The handler raises _UnauthorizedError when no driver wired; the
    # registry converts it to ToolResult(status='unauthorized'). At the
    # raw handler level we expect the exception.
    from selffork_orchestrator.tools.base import _UnauthorizedError

    with pytest.raises(_UnauthorizedError):
        await _ios_click(ctx_no_driver, IosClickArgs(x=0, y=0))
