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
from typing import Any, Literal

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

    platform: str = "android"

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
        if key_combo not in {
            "back",
            "home",
            "menu",
            "app_switch",
            "power",
            "volume_up",
            "volume_down",
        }:
            raise ValueError(f"unsupported android key combo {key_combo!r}")
        await self.mcp.press_key(key_combo)  # type: ignore[arg-type]

    async def install_apk(self, apk_path: Path) -> None:
        try:
            await self.mcp.install_apk(apk_path)
        except Exception:
            await self.fallback.install_apk(apk_path)

    async def ax_tree(self, bundle_id: str | None = None) -> dict[str, Any]:
        return await self.mcp.dump_a11y_tree()

    async def storage_state_save(self, provider: str, project_slug: str | None = None) -> None:
        raise NotImplementedError(
            "Android driver storage_state is not applicable; use cloud Account state instead"
        )

    async def storage_state_load(self, provider: str, project_slug: str | None = None) -> None:
        raise NotImplementedError("Android driver storage_state is not applicable")

    # ---- S-ToolFleet Faz 1 — interaction extensions ------------------

    async def double_click(self, x: int, y: int) -> None:
        await self.mcp.double_tap(x, y)

    async def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        await self.mcp.long_press(x, y, duration_ms=duration_ms)

    async def clear_text(self) -> None:
        await self.mcp.clear_text()

    async def pinch(self, scale: float, velocity: float = 1.0) -> None:
        # mobile-mcp doesn't expose pinch directly on Android; emulate with two
        # opposing swipes from the screen center. Best-effort fallback.
        cx = 540
        cy = 1000
        delta = int(200 * abs(scale - 1.0))
        if scale < 1.0:  # zoom out — fingers move toward center
            await self.mcp.swipe(cx - delta, cy, cx, cy)
            await self.mcp.swipe(cx + delta, cy, cx, cy)
        else:  # zoom in — fingers move away from center
            await self.mcp.swipe(cx, cy, cx - delta, cy)
            await self.mcp.swipe(cx, cy, cx + delta, cy)
        _ = velocity  # accepted for API parity; unused without true pinch

    async def press_button(self, name: str) -> None:
        # Map iOS-style names to Android press_key vocabulary
        mapping = {
            "back": "back",
            "home": "home",
            "menu": "menu",
            "app_switch": "app_switch",
            "recent": "app_switch",
            "power": "power",
            "lock": "power",
            "volume_up": "volume_up",
            "volume_down": "volume_down",
            "volumeup": "volume_up",
            "volumedown": "volume_down",
        }
        translated = mapping.get(name, name)
        await self.press_key(translated)

    # ---- lifecycle extensions ----------------------------------------

    async def app_terminate(self, package: str) -> None:
        await self.mcp.app_terminate(package)

    async def app_force_stop(self, package: str) -> str:
        return await self.fallback.app_force_stop(package)

    async def app_clear_data(self, package: str) -> str:
        return await self.fallback.app_clear_data(package)

    async def install_app(self, apk_path: Path) -> None:
        await self.install_apk(apk_path)

    async def install_multiple_apks(self, apk_paths: list[Path]) -> str:
        return await self.fallback.install_multiple_apks(apk_paths)

    async def uninstall_app(self, package: str) -> None:
        try:
            await self.mcp.uninstall_app(package)
        except Exception:
            await self.fallback.uninstall_app(package)

    async def list_apps(self) -> list[dict[str, Any]]:
        try:
            return await self.mcp.list_apps()
        except Exception:
            packages = await self.fallback.list_packages()
            return [{"package": p} for p in packages]

    async def app_activate(self, package: str) -> None:
        # Android has no distinct activate; launch handles both.
        await self.app_launch(package)

    # ---- system extensions -------------------------------------------

    async def get_clipboard(self) -> str:
        try:
            return await self.mcp.get_clipboard()
        except Exception:
            return await self.fallback.adb_shell("service call clipboard 1") or ""

    async def set_clipboard(self, text: str) -> None:
        await self.mcp.set_clipboard(text)

    async def get_orientation(self) -> str:
        try:
            return await self.mcp.get_orientation()
        except Exception:
            text = await self.fallback.adb_shell(
                "dumpsys input | grep SurfaceOrientation | head -1",
            )
            return text.strip()

    async def set_orientation(self, orientation: str) -> None:
        # 0=portrait, 1=landscape, 2=upside-down portrait, 3=landscape-rev
        rotation = {
            "PORTRAIT": "0",
            "LANDSCAPE": "1",
            "UPSIDE_DOWN": "2",
            "LANDSCAPE_REVERSE": "3",
            "portrait": "0",
            "landscape": "1",
        }.get(orientation, "0")
        await self.fallback.adb_shell(
            "settings put system accelerometer_rotation 0",
        )
        await self.fallback.adb_shell(
            f"settings put system user_rotation {rotation}",
        )

    async def get_property(self, key: str) -> str:
        return await self.fallback.get_property(key)

    async def set_property(self, key: str, value: str) -> str:
        return await self.fallback.set_property(key, value)

    async def reboot(self) -> None:
        await self.fallback.reboot()

    async def get_battery(self) -> dict[str, str]:
        return await self.fallback.get_battery()

    # ---- intents / shell / files / logs / deeplink -------------------

    async def intent(
        self,
        action: str,
        *,
        extras: dict[str, str] | None = None,
        component: str | None = None,
        data: str | None = None,
    ) -> str:
        return await self.fallback.intent(
            action,
            extras=extras,
            component=component,
            data=data,
        )

    async def broadcast(
        self,
        action: str,
        *,
        extras: dict[str, str] | None = None,
    ) -> str:
        return await self.fallback.broadcast(action, extras=extras)

    async def deeplink(self, url: str) -> str:
        return await self.fallback.deeplink(url)

    async def shell(self, command: str) -> str:
        return await self.fallback.adb_shell(command)

    async def dumpsys(self, service: str) -> str:
        return await self.fallback.dumpsys(service)

    async def logcat(
        self,
        *,
        tag_filter: str | None = None,
        max_lines: int = 200,
        clear: bool = False,
    ) -> str:
        return await self.fallback.logcat(
            tag_filter=tag_filter,
            max_lines=max_lines,
            clear=clear,
        )

    async def push(self, local: Path, remote: str) -> str:
        return await self.fallback.push(local, remote)

    async def pull(self, remote: str, local: Path) -> str:
        return await self.fallback.pull(remote, local)

    async def device_list(self) -> list[dict[str, str]]:
        return await self.fallback.list_devices()

    async def screenrecord_start(self, output_path: Path) -> None:
        await self.fallback.screenrecord_start(output_path)

    async def screenrecord_stop(self) -> Path | None:
        return await self.fallback.screenrecord_stop()

    async def set_geolocation(self, latitude: float, longitude: float) -> str:
        return await self.fallback.set_geolocation(latitude, longitude)
