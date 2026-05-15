"""Appium XCUITest adapter for iOS (M5 — ADR-005 §M5-C3).

Wraps Appium-Python-Client against an XCUITest driver session. Lazy import
so test environments without Appium installed can still import the module
for unit testing of the action surface contract.
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

    async def tap(self, x: int, y: int) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.tap, [(x, y)])

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

    async def type_text(self, text: str) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.execute_script, "mobile: type", {"text": text})

    async def press_key(self, key: str) -> None:
        import asyncio

        driver = self._require_driver()
        # XCUITest pressButton handles "home" / "volumeup" / "volumedown".
        await asyncio.to_thread(driver.execute_script, "mobile: pressButton", {"name": key})

    async def app_launch(self, bundle_id: str) -> None:
        import asyncio

        driver = self._require_driver()
        await asyncio.to_thread(driver.activate_app, bundle_id)

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
