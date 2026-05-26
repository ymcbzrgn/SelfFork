"""Vision Pro driver — visionOS simulator via xcrun simctl + AppleScript pointer.

S-ToolFleet Faz 4. Per ADR-010 §9.1 #3 operator lock: vision-only, no
Appium / XCTest. visionOS simulator runs on macOS; we drive it via:

* ``xcrun simctl`` for list/boot/shutdown/screenshot/launch/logs
* AppleScript ``click at {x, y}`` for host-Mac pointer clicks on the
  simulator window (best-effort; operator must keep the sim window
  visible + focused)
* ``ctx.vision_runtime`` (Gemma 4 VLM) for OCR-style text finding on
  screenshots — returns ``unwired`` status when no runtime is wired

Modalite-çift kabul: less surface than Quest, but honest about the
visionOS automation reality. visionOS XCTest is "Designed for iPad"
limited and Appium is not available on visionOS sim per 2026 status.
"""

from __future__ import annotations

from typing import Any

from selffork_body.drivers.desktop.macos.applescript_runner import AppleScriptRunner
from selffork_body.drivers.ios.simulator_runtime import IosSimulatorRuntime

__all__ = ["VisionProDriver"]


class VisionProDriver:
    """visionOS simulator driver — screenshot + simctl + AppleScript pointer."""

    platform: str = "visionpro"

    def __init__(
        self,
        *,
        device_id: str | None = None,
    ) -> None:
        # Reuse the iOS simulator runtime — visionOS sims use the same
        # ``xcrun simctl`` surface; the platform difference shows up in
        # the device list (runtime name contains "visionOS").
        self.simulator = IosSimulatorRuntime(
            device_id=device_id, ios_version="visionOS",
        )
        self._applescript = AppleScriptRunner()
        self._started = False

    async def start(self) -> None:
        self._started = True
        # Don't auto-boot — operator chooses simulator UDID via
        # visionpro_simulator_list / boot.

    async def stop(self) -> None:
        self._started = False

    async def screenshot(self, rect: tuple[int, int, int, int] | None = None) -> bytes:
        """Capture visionOS simulator frame via xcrun simctl."""
        return await self.simulator.screenshot()

    async def app_launch(self, bundle_id: str) -> None:
        await self.simulator.app_launch(bundle_id)

    async def simulator_list(self) -> list[dict[str, str]]:
        """Return only visionOS devices."""
        all_devices = await self.simulator.list_devices()
        return [d for d in all_devices if "vision" in d.get("runtime", "").lower()]

    async def simulator_boot(self, udid: str) -> str:
        return await self.simulator.boot_specific(udid)

    async def simulator_shutdown(self, udid: str) -> None:
        await self.simulator.shutdown_specific(udid)

    async def get_logs(
        self,
        *,
        predicate: str | None = None,
        last: str = "1m",
        udid: str | None = None,
    ) -> str:
        return await self.simulator.get_logs(
            predicate=predicate, last=last, udid=udid,
        )

    async def click_at(self, x: int, y: int) -> None:
        """Host-Mac pointer click at (x, y) — operator must focus the sim window.

        Uses AppleScript ``click at`` which moves the system cursor and
        clicks the topmost window underneath. Best-effort: visionOS sim
        must be the frontmost window for the click to land on it.
        """
        script = (
            f'tell application "System Events" to click at {{{x}, {y}}}'
        )
        await self._applescript.run(script, language="AppleScript")

    async def get_device_summary(self) -> dict[str, Any]:
        """One-shot summary of booted sim + screen geometry."""
        booted = self.simulator.booted_id
        return {
            "booted_udid": booted,
            "ios_version": self.simulator.ios_version,
        }
