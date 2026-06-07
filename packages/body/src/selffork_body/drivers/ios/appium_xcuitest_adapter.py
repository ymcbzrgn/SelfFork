"""Appium XCUITest adapter for iOS (M5 — ADR-005 §M5-C3, expanded S-ToolFleet Faz 1).

Wraps Appium-Python-Client against an XCUITest driver session. Lazy import
so test environments without Appium installed can still import the module
for unit testing of the action surface contract.

S-ToolFleet Faz 1 expansion: every iOS-DEEP tool operation routes through
this adapter — long-press, double-tap, clear-text, pinch, hardware
buttons, app lifecycle (launch/terminate/activate/install/uninstall/
state), clipboard, orientation, geolocation, deep links, settings, and
element queries. Methods that don't map to Appium's surface delegate
to ``IosSimulatorRuntime`` (simctl-level) instead.
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = ["AppiumXcuitestAdapter"]

_log = logging.getLogger(__name__)


class AppiumXcuitestAdapter:
    """Appium-Python-Client + XCUITest driver wrapper."""

    def __init__(
        self,
        *,
        device_udid: str,
        appium_url: str = "http://127.0.0.1:4723",
        ios_version: str = "17.2",
    ) -> None:
        self.device_udid = device_udid
        self.appium_url = appium_url
        self.ios_version = ios_version
        self._driver: Any | None = None

    async def start(self) -> None:
        try:
            from appium import webdriver as appium_webdriver
            from appium.options.ios import XCUITestOptions
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "AppiumXcuitestAdapter requires Appium-Python-Client; "
                "install via `uv pip install Appium-Python-Client>=5.0.0`."
            ) from exc

        options = XCUITestOptions()
        options.platform_name = "iOS"
        options.device_name = self.device_udid
        options.automation_name = "XCUITest"
        options.platform_version = self.ios_version
        # Synchronous Appium client; wrap with to_thread when used in async paths.
        self._driver = appium_webdriver.Remote(self.appium_url, options=options)

    async def stop(self) -> None:
        if self._driver is not None:
            self._driver.quit()
            self._driver = None

    def _require_driver(self) -> Any:
        if self._driver is None:
            raise RuntimeError("AppiumXcuitestAdapter: call start() first")
        return self._driver

    # ---- interaction --------------------------------------------------

    async def tap(self, x: int, y: int) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.tap, [(x, y)])

    async def double_tap(self, x: int, y: int) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(
            driver.execute_script,
            "mobile: doubleTap",
            {"x": x, "y": y},
        )

    async def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(
            driver.execute_script,
            "mobile: touchAndHold",
            {"x": x, "y": y, "duration": duration_ms / 1000.0},
        )

    async def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 250,
    ) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.swipe, start_x, start_y, end_x, end_y, duration_ms)

    async def pinch(self, scale: float, velocity: float = 1.0) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(
            driver.execute_script,
            "mobile: pinch",
            {"scale": scale, "velocity": velocity},
        )

    async def type_text(self, text: str) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.execute_script, "mobile: type", {"text": text})

    async def clear_text(self) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.execute_script, "mobile: clear", {})

    async def press_key(self, key: str) -> None:
        import asyncio

        driver = self._require_driver()
        # XCUITest pressButton handles "home" / "volumeup" / "volumedown".
        await asyncio.to_thread(driver.execute_script, "mobile: pressButton", {"name": key})

    async def press_button(self, name: str) -> None:
        """Alias for press_key, used by tools that name hardware buttons explicitly."""
        await self.press_key(name)

    # ---- app lifecycle ------------------------------------------------

    async def app_launch(self, bundle_id: str) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.activate_app, bundle_id)

    async def app_activate(self, bundle_id: str) -> None:
        await self.app_launch(bundle_id)

    async def app_terminate(self, bundle_id: str) -> bool:
        import asyncio

        driver = self._require_driver()
        return bool(
            await asyncio.to_thread(driver.terminate_app, bundle_id),
        )

    async def app_state(self, bundle_id: str) -> int:
        """0=not installed, 1=not running, 2=background suspended, 3=background, 4=foreground."""
        import asyncio

        driver = self._require_driver()
        return int(
            await asyncio.to_thread(driver.query_app_state, bundle_id),
        )

    async def install_app(self, app_path: str) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.install_app, app_path)

    async def uninstall_app(self, bundle_id: str) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.remove_app, bundle_id)

    async def is_app_installed(self, bundle_id: str) -> bool:
        import asyncio

        driver = self._require_driver()
        return bool(await asyncio.to_thread(driver.is_app_installed, bundle_id))

    async def app_background(self, seconds: float = -1) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.background_app, seconds)

    async def list_installed_apps(self) -> list[dict[str, Any]]:
        import asyncio

        driver = self._require_driver()
        result = await asyncio.to_thread(
            driver.execute_script,
            "mobile: installedApps",
            {},
        )
        return list(result or [])

    # ---- observation --------------------------------------------------

    async def screenshot(self) -> bytes:
        import asyncio
        import base64

        driver = self._require_driver()
        b64 = await asyncio.to_thread(driver.get_screenshot_as_base64)
        return base64.b64decode(b64)

    async def dump_a11y_tree(self) -> str:
        import asyncio

        driver = self._require_driver()
        return await asyncio.to_thread(lambda: driver.page_source)

    # ---- system / device ---------------------------------------------

    async def get_orientation(self) -> str:
        import asyncio

        driver = self._require_driver()
        return str(await asyncio.to_thread(lambda: driver.orientation))

    async def set_orientation(self, orientation: str) -> None:
        import asyncio

        driver = self._require_driver()

        # Appium's setter via property
        def _setter() -> None:
            driver.orientation = orientation

        await asyncio.to_thread(_setter)

    async def get_clipboard(self) -> str:
        import asyncio

        driver = self._require_driver()
        return str(await asyncio.to_thread(driver.get_clipboard_text))

    async def set_clipboard(self, text: str) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.set_clipboard_text, text)

    async def terminate_keyboard(self) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.hide_keyboard)

    # ---- deep links / settings / location ----------------------------

    async def open_url(self, url: str) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(
            driver.execute_script,
            "mobile: deepLink",
            {"url": url},
        )

    async def set_geolocation(
        self,
        latitude: float,
        longitude: float,
        altitude: float = 0.0,
    ) -> None:
        import asyncio

        driver = self._require_driver()

        def _setter() -> None:
            driver.set_location(latitude, longitude, altitude)

        await asyncio.to_thread(_setter)

    async def get_geolocation(self) -> dict[str, float]:
        import asyncio

        driver = self._require_driver()
        loc = await asyncio.to_thread(driver.location)
        return {
            "latitude": float(loc.get("latitude", 0.0)),
            "longitude": float(loc.get("longitude", 0.0)),
            "altitude": float(loc.get("altitude", 0.0)),
        }

    async def set_setting(self, name: str, value: Any) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(
            driver.execute_script,
            "mobile: updateSafariPreferences",
            {name: value},
        )

    async def get_settings(self) -> dict[str, Any]:
        import asyncio

        driver = self._require_driver()
        result = await asyncio.to_thread(lambda: driver.get_settings())
        return dict(result or {})

    # ---- element queries (for ui_verify_*) ---------------------------

    async def find_element(self, by: str, value: str) -> dict[str, Any]:
        import asyncio

        driver = self._require_driver()

        def _find() -> dict[str, Any]:
            el = driver.find_element(by, value)
            return {
                "id": getattr(el, "id", None),
                "tag_name": getattr(el, "tag_name", None),
                "text": getattr(el, "text", None),
                "displayed": el.is_displayed(),
                "enabled": el.is_enabled(),
                "selected": el.is_selected(),
                "rect": el.rect if hasattr(el, "rect") else None,
            }

        return await asyncio.to_thread(_find)

    async def get_active_element(self) -> dict[str, Any]:
        import asyncio

        driver = self._require_driver()

        def _active() -> dict[str, Any]:
            el = driver.switch_to.active_element
            return {
                "id": getattr(el, "id", None),
                "tag_name": getattr(el, "tag_name", None),
                "text": getattr(el, "text", None),
            }

        return await asyncio.to_thread(_active)
