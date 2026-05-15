"""iOS driver (M5 — ADR-005 §M5-C3).

Simulator-first; real device path raises ``NotImplementedError`` until M6
once Apple Developer Program enrollment is in place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

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
