"""iOS driver (M5 — ADR-005 §M5-C3).

Simulator-first; real device path raises ``NotImplementedError`` until M6
once Apple Developer Program enrollment is in place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from selffork_body.drivers.ios.appium_xcuitest_adapter import AppiumXcuitestAdapter
from selffork_body.drivers.ios.simulator_runtime import (
    IosSimulatorError,
    IosSimulatorRuntime,
)

__all__ = [
    "AppiumXcuitestAdapter",
    "IosDriver",
    "IosSimulatorError",
    "IosSimulatorRuntime",
]


class IosDriver:
    """Unified iOS driver. Simulator runtime + Appium XCUITest adapter."""

    platform: str = "ios"

    def __init__(
        self,
        *,
        runtime: Literal["sim", "physical"] = "sim",
        device_id: str | None = None,
        ios_version: str = "17.2",
        appium: AppiumXcuitestAdapter | None = None,
    ) -> None:
        if runtime == "physical":
            raise NotImplementedError(
                "iOS real-device support lands in M6 ($99/yr Apple Developer Program required)"
            )
        self.runtime_kind = runtime
        self.simulator = IosSimulatorRuntime(device_id=device_id, ios_version=ios_version)
        self._appium = appium

    async def start(self) -> None:
        await self.simulator.boot()
        if self._appium is None:
            self._appium = AppiumXcuitestAdapter(
                device_udid=self.simulator.booted_id or "booted",
                ios_version=self.simulator.ios_version,
            )
        await self._appium.start()

    async def stop(self) -> None:
        if self._appium is not None:
            await self._appium.stop()
        await self.simulator.shutdown()

    async def click(
        self,
        target: str,
        bbox: tuple[int, int, int, int] | None = None,
        button: str = "left",
    ) -> None:
        if bbox is None:
            raise ValueError("IosDriver.click requires bbox; resolve via vision/AX first")
        cx = bbox[0] + bbox[2] // 2
        cy = bbox[1] + bbox[3] // 2
        if self._appium is None:
            raise RuntimeError("driver not started")
        await self._appium.tap(cx, cy)

    async def type_text(self, text: str, target: str | None = None) -> None:
        if self._appium is None:
            raise RuntimeError("driver not started")
        await self._appium.type_text(text)

    async def screenshot(self, rect: tuple[int, int, int, int] | None = None) -> bytes:
        return await self.simulator.screenshot()

    async def scroll(self, direction: str = "down", amount: int = 300) -> None:
        if self._appium is None:
            raise RuntimeError("driver not started")
        cx = 195
        if direction == "down":
            await self._appium.swipe(cx, 700, cx, 700 - amount)
        elif direction == "up":
            await self._appium.swipe(cx, 200, cx, 200 + amount)
        elif direction == "left":
            await self._appium.swipe(350, 400, 350 - amount, 400)
        elif direction == "right":
            await self._appium.swipe(50, 400, 50 + amount, 400)
        else:
            raise ValueError(f"unsupported scroll direction {direction!r}")

    async def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 250,
    ) -> None:
        if self._appium is None:
            raise RuntimeError("driver not started")
        await self._appium.swipe(start_x, start_y, end_x, end_y, duration_ms=duration_ms)

    async def app_launch(self, bundle_id: str) -> None:
        if self._appium is not None:
            await self._appium.app_launch(bundle_id)
        else:
            await self.simulator.app_launch(bundle_id)

    async def press_key(self, key_combo: str) -> None:
        if self._appium is None:
            raise RuntimeError("driver not started")
        await self._appium.press_key(key_combo)

    async def biometric_match(self) -> None:
        await self.simulator.biometric_match()

    async def biometric_no_match(self) -> None:
        await self.simulator.biometric_no_match()

    async def install_apk(self, apk_path: Path) -> None:
        raise NotImplementedError("iOS uses .app/.ipa via simulator.app_install(); not APK")

    async def ax_tree(self, bundle_id: str | None = None) -> str:
        if self._appium is None:
            raise RuntimeError("driver not started")
        return await self._appium.dump_a11y_tree()

    async def storage_state_save(self, provider: str, project_slug: str | None = None):  # type: ignore[no-untyped-def]
        raise NotImplementedError(
            "iOS storage_state is per-app and managed by simulator state; not exposed here"
        )

    async def storage_state_load(self, provider: str, project_slug: str | None = None):  # type: ignore[no-untyped-def]
        raise NotImplementedError("iOS storage_state load not supported in M5")

    # ---- S-ToolFleet Faz 1 — interaction extensions ------------------

    def _ready_appium(self) -> AppiumXcuitestAdapter:
        if self._appium is None:
            raise RuntimeError("driver not started")
        return self._appium

    async def double_click(self, x: int, y: int) -> None:
        await self._ready_appium().double_tap(x, y)

    async def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        await self._ready_appium().long_press(x, y, duration_ms=duration_ms)

    async def clear_text(self) -> None:
        await self._ready_appium().clear_text()

    async def pinch(self, scale: float, velocity: float = 1.0) -> None:
        await self._ready_appium().pinch(scale, velocity=velocity)

    async def press_button(self, name: str) -> None:
        await self._ready_appium().press_button(name)

    # ---- lifecycle extensions ----------------------------------------

    async def app_terminate(self, bundle_id: str) -> bool:
        return await self._ready_appium().app_terminate(bundle_id)

    async def app_activate(self, bundle_id: str) -> None:
        await self._ready_appium().app_activate(bundle_id)

    async def app_state(self, bundle_id: str) -> int:
        return await self._ready_appium().app_state(bundle_id)

    async def install_app(self, app_path: str) -> None:
        await self._ready_appium().install_app(app_path)

    async def uninstall_app(self, bundle_id: str) -> None:
        await self._ready_appium().uninstall_app(bundle_id)

    async def is_app_installed(self, bundle_id: str) -> bool:
        return await self._ready_appium().is_app_installed(bundle_id)

    async def app_background(self, seconds: float = -1) -> None:
        await self._ready_appium().app_background(seconds=seconds)

    async def list_apps(self) -> list[dict[str, Any]]:
        return await self._ready_appium().list_installed_apps()

    # ---- system extensions -------------------------------------------

    async def get_orientation(self) -> str:
        return await self._ready_appium().get_orientation()

    async def set_orientation(self, orientation: str) -> None:
        await self._ready_appium().set_orientation(orientation)

    async def get_clipboard(self) -> str:
        return await self._ready_appium().get_clipboard()

    async def set_clipboard(self, text: str) -> None:
        await self._ready_appium().set_clipboard(text)

    async def terminate_keyboard(self) -> None:
        await self._ready_appium().terminate_keyboard()

    # ---- network / deeplink / location -------------------------------

    async def open_url(self, url: str) -> None:
        # Prefer Appium deepLink; simctl openurl as fallback when no driver.
        try:
            await self._ready_appium().open_url(url)
        except RuntimeError:
            await self.simulator.open_url(url)

    async def set_geolocation(
        self,
        latitude: float,
        longitude: float,
        altitude: float = 0.0,
    ) -> None:
        try:
            await self._ready_appium().set_geolocation(latitude, longitude, altitude=altitude)
        except RuntimeError:
            await self.simulator.set_geolocation(latitude, longitude)

    async def get_geolocation(self) -> dict[str, float]:
        return await self._ready_appium().get_geolocation()

    # ---- simulator-level (simctl) ------------------------------------

    async def simulator_list(self) -> list[dict[str, str]]:
        return await self.simulator.list_devices()

    async def simulator_boot(self, udid: str) -> str:
        return await self.simulator.boot_specific(udid)

    async def simulator_shutdown(self, udid: str) -> None:
        await self.simulator.shutdown_specific(udid)

    async def simulator_erase(self, udid: str) -> None:
        await self.simulator.erase_specific(udid)

    async def get_logs(
        self,
        predicate: str | None = None,
        last: str | None = None,
    ) -> str:
        return await self.simulator.get_logs(predicate=predicate, last=last)

    async def send_push_notification(self, payload_path: Path, bundle_id: str) -> None:
        await self.simulator.push_notification(payload_path, bundle_id)

    async def record_video_start(self, output_path: Path) -> None:
        await self.simulator.record_video_start(output_path)

    async def record_video_stop(self) -> Path | None:
        return await self.simulator.record_video_stop()

    async def status_bar_override(
        self,
        time: str | None = None,
        battery_state: str | None = None,
        cellular_bars: int | None = None,
        wifi_bars: int | None = None,
    ) -> None:
        await self.simulator.status_bar_override(
            time=time,
            battery_state=battery_state,
            cellular_bars=cellular_bars,
            wifi_bars=wifi_bars,
        )

    async def set_appearance(self, appearance: str) -> None:
        await self.simulator.set_appearance(appearance)

    # ---- element queries ---------------------------------------------

    async def find_element(self, by: str, value: str) -> dict[str, Any]:
        return await self._ready_appium().find_element(by, value)

    async def get_active_element(self) -> dict[str, Any]:
        return await self._ready_appium().get_active_element()
