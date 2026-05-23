"""Playwright-backed web driver for the M5 Body pillar (ADR-005 §M5-C1).

Runs a Chromium browser via Playwright's async API; the driver exposes the
full ``WebDriver`` action surface (``goto / click / type / screenshot /
scroll / press_key / wait / storage_state_*``). Locator strategy is
DOM-first via :func:`extract_dom_tree`; vision fallback is layered above
this driver in :class:`selffork_body.vision.VisionOrchestrator`.

Playwright is imported lazily inside :meth:`start` so test environments
without the package can still import the module for unit testing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal, cast

from selffork_body.drivers.web.dom_extractor import extract_dom_tree
from selffork_body.drivers.web.security_watchdog import SecurityWatchdog
from selffork_body.drivers.web.storage_state import (
    StorageStateAutoSave,
    WebStorageStateManager,
)

__all__ = ["PlaywrightWebDriver"]

_log = logging.getLogger(__name__)


class PlaywrightWebDriver:
    """Playwright + Chromium driver. Lazy import; warden gating is the caller's job."""

    def __init__(
        self,
        *,
        headless: bool = True,
        storage_state_path: Path | None = None,
        allowed_domains: set[str] | None = None,
        provider: str | None = None,
        project_slug: str | None = None,
        storage_root: Path | None = None,
    ) -> None:
        self.headless = headless
        self.storage_state_path = storage_state_path
        self.provider = provider
        self.project_slug = project_slug
        self.storage = WebStorageStateManager(root=storage_root)
        self.security = SecurityWatchdog(allowed_domains=allowed_domains)
        # Playwright handles are typed ``Any`` because the package is
        # imported lazily inside ``start()`` and mypy can't see the
        # concrete types under ``ignore_missing_imports`` (CI / dev
        # boxes without the optional dep).
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._autosave: StorageStateAutoSave | None = None

    @property
    def started(self) -> bool:
        return self._page is not None

    async def start(self) -> None:
        if self.started:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "PlaywrightWebDriver requires the `playwright` package. "
                "Install via `uv pip install playwright && playwright install chromium`."
            ) from exc
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless
        )
        ctx_kwargs: dict[str, Any] = {}
        if self.storage_state_path is not None and self.storage_state_path.exists():
            ctx_kwargs["storage_state"] = str(self.storage_state_path)
        self._context = await self._browser.new_context(**ctx_kwargs)
        self._page = await self._context.new_page()
        # Wire navigation watchdog
        self._page.on(
            "framenavigated",
            lambda frame: self._page.context._loop.create_task(
                self.security.on_framenavigated(frame)
            ),
        )
        if self.provider is not None:
            self._autosave = StorageStateAutoSave(
                manager=self.storage,
                context=self._context,
                provider=self.provider,
                project_slug=self.project_slug,
            )
            await self._autosave.start()

    async def stop(self) -> None:
        if self._autosave is not None:
            await self._autosave.stop()
            self._autosave = None
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self._page = None

    def _require_page(self) -> Any:
        if self._page is None:
            raise RuntimeError("PlaywrightWebDriver: call start() first")
        return self._page

    async def goto(self, url: str) -> None:
        page = self._require_page()
        if not self.security.is_allowed(url):
            raise PermissionError(f"navigate to {url!r} blocked by security watchdog")
        await page.goto(url)

    async def click(
        self,
        target: str,
        bbox: tuple[int, int, int, int] | None = None,
        button: Literal["left", "right"] = "left",
    ) -> None:
        page = self._require_page()
        if bbox is not None:
            cx = bbox[0] + bbox[2] // 2
            cy = bbox[1] + bbox[3] // 2
            await page.mouse.click(cx, cy, button=button)
            return
        # DOM-first: try as a CSS selector. If invalid, fall through to text matching.
        try:
            await page.click(target, button=button, timeout=5000)
        except Exception:
            await page.get_by_text(target, exact=False).first.click(button=button)

    async def type_text(self, text: str, target: str | None = None) -> None:
        page = self._require_page()
        if target:
            try:
                await page.fill(target, text)
                return
            except Exception:
                pass
        await page.keyboard.type(text)

    async def screenshot(self, rect: tuple[int, int, int, int] | None = None) -> bytes:
        page = self._require_page()
        if rect is not None:
            return cast(
                bytes,
                await page.screenshot(
                    clip={
                        "x": rect[0],
                        "y": rect[1],
                        "width": rect[2],
                        "height": rect[3],
                    },
                    type="png",
                ),
            )
        return cast(bytes, await page.screenshot(full_page=True, type="png"))

    async def scroll(self, direction: str = "down", amount: int = 300) -> None:
        page = self._require_page()
        dx, dy = 0, 0
        if direction == "down":
            dy = amount
        elif direction == "up":
            dy = -amount
        elif direction == "left":
            dx = -amount
        elif direction == "right":
            dx = amount
        elif direction == "top":
            await page.evaluate("window.scrollTo(0, 0)")
            return
        elif direction == "bottom":
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return
        await page.mouse.wheel(dx, dy)

    async def press_key(self, key_combo: str) -> None:
        page = self._require_page()
        await page.keyboard.press(key_combo)

    async def wait_for(self, selector: str, timeout: float = 5.0) -> None:
        page = self._require_page()
        await page.wait_for_selector(selector, timeout=int(timeout * 1000))

    async def evaluate(self, js_code: str) -> Any:
        """Run arbitrary JS — caller must gate at T2 risk_tier."""
        page = self._require_page()
        return await page.evaluate(js_code)

    async def dump_dom_tree(self) -> list[dict[str, Any]]:
        return await extract_dom_tree(self._require_page())

    async def storage_state_save(
        self,
        provider: str | None = None,
        project_slug: str | None = None,
    ) -> Path:
        if self._context is None:
            raise RuntimeError("driver not started; storage_state_save unavailable")
        provider = provider or self.provider
        if provider is None:
            raise ValueError("provider must be set on driver or arg")
        slug = project_slug if project_slug is not None else self.project_slug
        return await self.storage.save(self._context, provider, slug)

    async def storage_state_load(
        self,
        provider: str | None = None,
        project_slug: str | None = None,
    ) -> bool:
        provider = provider or self.provider
        if provider is None:
            raise ValueError("provider must be set on driver or arg")
        slug = project_slug if project_slug is not None else self.project_slug
        path = self.storage.load_path(provider, slug)
        return path is not None
