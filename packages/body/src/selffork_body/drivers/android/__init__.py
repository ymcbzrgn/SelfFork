"""Android driver (M5 — ADR-005 §M5-C2).

Three-layer stack:

* **Runtime**: :class:`DockerAndroidRuntime` (budtmo) container or pure ADB
  to a physical/Genymotion target.
* **Action surface**: :class:`MobileMcpAdapter` for tap/swipe/type/screenshot.
* **Fallback**: :class:`UiAutomator2Fallback` for pixel-perfect screenshot +
  ADB shell when mobile-mcp can't reach the surface.

The unified :class:`AndroidDriver` orchestrates the three; sessions consume
the driver via :class:`selffork_orchestrator.tools.body` ``body_*`` tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from selffork_body.drivers.android.docker_runtime import (
    AndroidRuntimeError,
    DockerAndroidRuntime,
)
from selffork_body.drivers.android.mobile_mcp_adapter import MobileMcpAdapter
from selffork_body.drivers.android.uiautomator2_fallback import UiAutomator2Fallback

__all__ = [
    "AndroidDriver",
    "AndroidRuntimeError",
    "DockerAndroidRuntime",
    "MobileMcpAdapter",
    "UiAutomator2Fallback",
]


class AndroidDriver:
    """Unified Android driver. Composes runtime + mobile-mcp + uiautomator2."""

    def __init__(
        self,
        *,
        runtime: Literal["docker", "physical"] = "docker",
        runtime_obj: DockerAndroidRuntime | None = None,
        mcp: MobileMcpAdapter | None = None,
        fallback: UiAutomator2Fallback | None = None,
        device_serial: str | None = None,
    ) -> None:
        self.runtime_kind = runtime
        self.runtime = runtime_obj or (DockerAndroidRuntime() if runtime == "docker" else None)
        self.mcp = mcp or MobileMcpAdapter()
        self.fallback = fallback or UiAutomator2Fallback(device_serial=device_serial)
        self.device_serial = device_serial

    async def start(self) -> None:
        if self.runtime is not None and not self.runtime.started:
            await self.runtime.start()
            await self.runtime.wait_for_boot()

    async def stop(self) -> None:
        # M5 audit-fix: ensure runtime.stop() runs even when mcp.close() raises;
        # otherwise an httpx teardown error leaks the docker container.
        try:
            await self.mcp.close()
        finally:
            if self.runtime is not None and self.runtime.started:
                await self.runtime.stop()

    # ---- action surface — delegate primarily to mobile-mcp ----

    async def click(
        self,
        target: str,
        bbox: tuple[int, int, int, int] | None = None,
        button: str = "left",
    ) -> None:
        if bbox is None:
            raise ValueError("AndroidDriver.click requires bbox; resolve via vision/AX first")
        cx = bbox[0] + bbox[2] // 2
        cy = bbox[1] + bbox[3] // 2
        await self.mcp.tap(cx, cy)

    async def type_text(self, text: str, target: str | None = None) -> None:
        await self.mcp.type_text(text)

    async def screenshot(self, rect: tuple[int, int, int, int] | None = None) -> bytes:
        if rect is None:
            return await self.mcp.screenshot()
        return await self.fallback.screenshot()

    async def scroll(self, direction: str = "down", amount: int = 300) -> None:
        cx = 540
        if direction == "down":
            await self.mcp.swipe(cx, 1500, cx, 1500 - amount)
        elif direction == "up":
            await self.mcp.swipe(cx, 500, cx, 500 + amount)
        elif direction == "left":
            await self.mcp.swipe(800, 960, 800 - amount, 960)
        elif direction == "right":
            await self.mcp.swipe(280, 960, 280 + amount, 960)
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
        await self.mcp.swipe(start_x, start_y, end_x, end_y, duration_ms=duration_ms)

    async def app_launch(self, bundle_id: str) -> None:
        await self.mcp.app_launch(bundle_id)

    async def press_key(self, key_combo: str) -> None:
        if key_combo not in {"back", "home", "menu", "app_switch", "power", "volume_up", "volume_down"}:
            raise ValueError(f"unsupported android key combo {key_combo!r}")
        await self.mcp.press_key(key_combo)  # type: ignore[arg-type]

    async def install_apk(self, apk_path: Path) -> None:
        try:
            await self.mcp.install_apk(apk_path)
        except Exception:
            await self.fallback.install_apk(apk_path)

    async def ax_tree(self, bundle_id: str | None = None) -> dict:
        return await self.mcp.dump_a11y_tree()

    async def storage_state_save(self, provider: str, project_slug: str | None = None):  # type: ignore[no-untyped-def]
        raise NotImplementedError("Android driver storage_state is not applicable; use cloud Account state instead")

    async def storage_state_load(self, provider: str, project_slug: str | None = None):  # type: ignore[no-untyped-def]
        raise NotImplementedError("Android driver storage_state is not applicable")
