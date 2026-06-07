"""Shared stubs + fixtures for mobile tool tests."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from selffork_body.sandbox import PermissionWarden, WardenMode
from selffork_orchestrator.tools.base import ToolContext


class _StubProjectStore:
    pass


@dataclass
class StubMobileDriver:
    """Stub mobile driver that records every method call.

    Satisfies the IosDriver / AndroidDriver duck-typed contract used by
    the mobile tool handlers. Set ``platform`` to test platform-routing.
    """

    platform: str = "ios"
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)

    def _record(self, name: str, args: tuple, kwargs: dict) -> None:
        self.calls.append((name, args, dict(kwargs)))

    # Composite-mode support: tools that look for .ios / .android attrs
    ios: StubMobileDriver | None = None
    android: StubMobileDriver | None = None

    # --- iOS / generic methods --------------------------------------------
    async def screenshot(self, rect=None):
        self._record("screenshot", (), {"rect": rect})
        return b"\x89PNG\r\n\x1a\nstub"

    async def ax_tree(self, bundle_id=None):
        self._record("ax_tree", (), {"bundle_id": bundle_id})
        return (
            '<XCUIElementTypeApplication name="Demo" visible="true" enabled="true" '
            'focused="true" selected="true" checked="true">\n'
            "  <XCUIElementTypeButton "
            'name="Submit" displayed="true">Submit</XCUIElementTypeButton>\n'
            "  <XCUIElementTypeStaticText "
            'name="Welcome">Welcome to SelfFork</XCUIElementTypeStaticText>\n'
            "</XCUIElementTypeApplication>"
        )

    async def double_click(self, x, y):
        self._record("double_click", (x, y), {})

    async def long_press(self, x, y, duration_ms=800):
        self._record("long_press", (x, y), {"duration_ms": duration_ms})

    async def clear_text(self):
        self._record("clear_text", (), {})

    async def pinch(self, scale, velocity=1.0):
        self._record("pinch", (scale,), {"velocity": velocity})

    async def press_button(self, name):
        self._record("press_button", (name,), {})

    async def press_key(self, key_combo):
        self._record("press_key", (key_combo,), {})

    async def scroll(self, direction="down", amount=300):
        self._record("scroll", (), {"direction": direction, "amount": amount})

    async def type_text(self, text, target=None):
        self._record("type_text", (text,), {"target": target})

    async def swipe(self, sx, sy, ex, ey, duration_ms=250):
        self._record("swipe", (sx, sy, ex, ey), {"duration_ms": duration_ms})

    async def app_launch(self, bundle_id):
        self._record("app_launch", (bundle_id,), {})

    async def app_terminate(self, bundle_id):
        self._record("app_terminate", (bundle_id,), {})
        return True

    async def app_activate(self, bundle_id):
        self._record("app_activate", (bundle_id,), {})

    async def app_state(self, bundle_id):
        self._record("app_state", (bundle_id,), {})
        return 4

    async def install_app(self, path):
        self._record("install_app", (path,), {})

    async def uninstall_app(self, bundle_id):
        self._record("uninstall_app", (bundle_id,), {})

    async def app_background(self, seconds=-1):
        self._record("app_background", (), {"seconds": seconds})

    async def list_apps(self):
        self._record("list_apps", (), {})
        return [{"bundleId": "com.example.app", "name": "Example"}]

    async def get_orientation(self):
        self._record("get_orientation", (), {})
        return "PORTRAIT"

    async def set_orientation(self, orientation):
        self._record("set_orientation", (orientation,), {})

    async def get_clipboard(self):
        self._record("get_clipboard", (), {})
        return "clip"

    async def set_clipboard(self, text):
        self._record("set_clipboard", (text,), {})

    async def terminate_keyboard(self):
        self._record("terminate_keyboard", (), {})

    async def open_url(self, url):
        self._record("open_url", (url,), {})

    async def set_geolocation(self, lat, lon, altitude=0.0):
        self._record("set_geolocation", (lat, lon), {"altitude": altitude})
        # Android variant returns str
        return "OK"

    async def get_geolocation(self):
        self._record("get_geolocation", (), {})
        return {"latitude": 1.0, "longitude": 2.0, "altitude": 0.0}

    async def simulator_list(self):
        self._record("simulator_list", (), {})
        return [{"name": "iPhone 15", "udid": "AAA", "state": "Booted", "runtime": "iOS 17.0"}]

    async def simulator_boot(self, udid):
        self._record("simulator_boot", (udid,), {})
        return udid

    async def simulator_shutdown(self, udid):
        self._record("simulator_shutdown", (udid,), {})

    async def simulator_erase(self, udid):
        self._record("simulator_erase", (udid,), {})

    async def biometric_match(self):
        self._record("biometric_match", (), {})

    async def biometric_no_match(self):
        self._record("biometric_no_match", (), {})

    async def get_logs(self, predicate=None, last=None):
        self._record("get_logs", (), {"predicate": predicate, "last": last})
        return "log line 1\nlog line 2"

    async def send_push_notification(self, payload_path, bundle_id):
        self._record("send_push_notification", (payload_path, bundle_id), {})

    async def record_video_start(self, output_path):
        self._record("record_video_start", (output_path,), {})

    async def record_video_stop(self):
        self._record("record_video_stop", (), {})
        from pathlib import Path

        return Path("/tmp/recording.mp4")

    async def status_bar_override(
        self,
        time=None,
        battery_state=None,
        cellular_bars=None,
        wifi_bars=None,
    ):
        self._record(
            "status_bar_override",
            (),
            {
                "time": time,
                "battery_state": battery_state,
                "cellular_bars": cellular_bars,
                "wifi_bars": wifi_bars,
            },
        )

    async def set_appearance(self, appearance):
        self._record("set_appearance", (appearance,), {})

    async def find_element(self, by, value):
        self._record("find_element", (by, value), {})
        return {"id": "el-1", "text": "found", "displayed": True}

    async def get_active_element(self):
        self._record("get_active_element", (), {})
        return {"id": "el-active", "tag_name": "Button", "text": "Active"}

    # --- Android-specific -------------------------------------------------

    async def app_force_stop(self, package):
        self._record("app_force_stop", (package,), {})
        return ""

    async def app_clear_data(self, package):
        self._record("app_clear_data", (package,), {})
        return ""

    async def get_property(self, key):
        self._record("get_property", (key,), {})
        return "value"

    async def set_property(self, key, value):
        self._record("set_property", (key, value), {})
        return ""

    async def reboot(self):
        self._record("reboot", (), {})

    async def get_battery(self):
        self._record("get_battery", (), {})
        return {"level": "85", "status": "Charging"}

    async def intent(self, action, *, extras=None, component=None, data=None):
        self._record(
            "intent",
            (action,),
            {
                "extras": extras,
                "component": component,
                "data": data,
            },
        )
        return "Starting intent"

    async def broadcast(self, action, *, extras=None):
        self._record("broadcast", (action,), {"extras": extras})
        return "Broadcasting"

    async def deeplink(self, url):
        self._record("deeplink", (url,), {})
        return "Started"

    async def shell(self, command):
        self._record("shell", (command,), {})
        return "shell output"

    async def dumpsys(self, service):
        self._record("dumpsys", (service,), {})
        return "dumpsys " + service

    async def logcat(self, *, tag_filter=None, max_lines=200, clear=False):
        self._record(
            "logcat",
            (),
            {
                "tag_filter": tag_filter,
                "max_lines": max_lines,
                "clear": clear,
            },
        )
        return "log " * 5

    async def push(self, local, remote):
        self._record("push", (local, remote), {})
        return ""

    async def pull(self, remote, local):
        self._record("pull", (remote, local), {})
        return ""

    async def device_list(self):
        self._record("device_list", (), {})
        return [{"serial": "emulator-5554", "state": "device", "model": "Pixel_6"}]

    async def screenrecord_start(self, output_path):
        self._record("screenrecord_start", (output_path,), {})

    async def screenrecord_stop(self):
        self._record("screenrecord_stop", (), {})
        from pathlib import Path

        return Path("/tmp/screenrecord.mp4")


@pytest.fixture
def stub_ios_driver() -> StubMobileDriver:
    return StubMobileDriver(platform="ios")


@pytest.fixture
def stub_android_driver() -> StubMobileDriver:
    return StubMobileDriver(platform="android")


@pytest.fixture
def stub_composite_driver() -> StubMobileDriver:
    ios = StubMobileDriver(platform="ios")
    android = StubMobileDriver(platform="android")
    return StubMobileDriver(platform="composite", ios=ios, android=android)


@pytest.fixture
def permissive_warden() -> PermissionWarden:
    return PermissionWarden(mode=WardenMode.DANGER_FULL_ACCESS)


def make_ctx(
    *,
    driver: StubMobileDriver | None = None,
    warden: PermissionWarden | None = None,
    audit_logger: object | None = None,
    screenshot_store: object | None = None,
    session_id: str = "sess-test",
    project_slug: str | None = None,
) -> ToolContext:
    if warden is None and driver is not None:
        warden = PermissionWarden(mode=WardenMode.DANGER_FULL_ACCESS)
    return ToolContext(
        session_id=session_id,
        project_slug=project_slug,
        project_store=_StubProjectStore(),
        body_driver=driver,
        permission_warden=warden,
        audit_logger=audit_logger,
        screenshot_store=screenshot_store,
    )


@pytest.fixture
def ctx_ios(stub_ios_driver, permissive_warden) -> ToolContext:
    return make_ctx(driver=stub_ios_driver, warden=permissive_warden)


@pytest.fixture
def ctx_android(stub_android_driver, permissive_warden) -> ToolContext:
    return make_ctx(driver=stub_android_driver, warden=permissive_warden)


@pytest.fixture
def ctx_composite(stub_composite_driver, permissive_warden) -> ToolContext:
    return make_ctx(driver=stub_composite_driver, warden=permissive_warden)


@pytest.fixture
def ctx_no_driver() -> ToolContext:
    return make_ctx(driver=None, warden=None)
