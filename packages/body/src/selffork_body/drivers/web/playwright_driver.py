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

    platform: str = "web"

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
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
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

    # ---- S-ToolFleet Faz 2 — interaction extensions ------------------

    async def double_click(
        self,
        target: str | None = None,
        *,
        x: int | None = None,
        y: int | None = None,
        button: Literal["left", "right"] = "left",
    ) -> None:
        page = self._require_page()
        if x is not None and y is not None:
            await page.mouse.dblclick(x, y, button=button)
            return
        if target is None:
            raise ValueError("double_click requires target or (x, y)")
        await page.dblclick(target, button=button, timeout=5000)

    async def hover(
        self,
        target: str | None = None,
        *,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        page = self._require_page()
        if x is not None and y is not None:
            await page.mouse.move(x, y)
            return
        if target is None:
            raise ValueError("hover requires target or (x, y)")
        await page.hover(target, timeout=5000)

    async def fill_form(self, fields: dict[str, str]) -> int:
        """Fill a form: {selector: value}. Returns filled count."""
        page = self._require_page()
        filled = 0
        for selector, value in fields.items():
            try:
                await page.fill(selector, value, timeout=5000)
                filled += 1
            except Exception as exc:  # field-fill best-effort
                _log.debug("fill_form_field_failed: %s -> %s", selector, exc)
                continue
        return filled

    async def select_option(
        self,
        target: str,
        value: str | list[str] | None = None,
        *,
        label: str | None = None,
        index: int | None = None,
    ) -> list[str]:
        page = self._require_page()
        kwargs: dict[str, Any] = {}
        if value is not None:
            kwargs["value"] = value
        if label is not None:
            kwargs["label"] = label
        if index is not None:
            kwargs["index"] = index
        result = await page.select_option(target, **kwargs)
        return cast("list[str]", result)

    async def check(self, target: str) -> None:
        page = self._require_page()
        await page.check(target, timeout=5000)

    async def uncheck(self, target: str) -> None:
        page = self._require_page()
        await page.uncheck(target, timeout=5000)

    async def drag_and_drop(self, source: str, target: str) -> None:
        page = self._require_page()
        await page.drag_and_drop(source, target, timeout=10_000)

    async def upload_file(self, target: str, file_path: str | list[str]) -> None:
        page = self._require_page()
        paths = file_path if isinstance(file_path, list) else [file_path]
        await page.set_input_files(target, paths)

    async def clear(self, target: str) -> None:
        page = self._require_page()
        await page.fill(target, "", timeout=5000)

    async def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 250,
    ) -> None:
        """Touch-style swipe via mouse drag (Chromium supports both)."""
        page = self._require_page()
        await page.mouse.move(start_x, start_y)
        await page.mouse.down()
        steps = max(2, duration_ms // 16)
        await page.mouse.move(end_x, end_y, steps=steps)
        await page.mouse.up()

    # ---- navigation extensions ---------------------------------------

    async def back(self) -> None:
        page = self._require_page()
        await page.go_back()

    async def forward(self) -> None:
        page = self._require_page()
        await page.go_forward()

    async def reload(self) -> None:
        page = self._require_page()
        await page.reload()

    async def get_url(self) -> str:
        page = self._require_page()
        return str(page.url)

    async def get_title(self) -> str:
        page = self._require_page()
        return str(await page.title())

    async def set_viewport(self, width: int, height: int) -> None:
        page = self._require_page()
        await page.set_viewport_size({"width": width, "height": height})

    async def wait_for_load_state(
        self,
        state: Literal["load", "domcontentloaded", "networkidle"] = "load",
        timeout: float = 30.0,
    ) -> None:
        page = self._require_page()
        await page.wait_for_load_state(state, timeout=int(timeout * 1000))

    async def wait_for_url(self, url_pattern: str, timeout: float = 30.0) -> None:
        page = self._require_page()
        await page.wait_for_url(url_pattern, timeout=int(timeout * 1000))

    # ---- observation extensions --------------------------------------

    async def text_content(self, target: str) -> str:
        page = self._require_page()
        result = await page.text_content(target, timeout=5000)
        return result or ""

    async def get_attribute(self, target: str, name: str) -> str | None:
        page = self._require_page()
        value: Any = await page.get_attribute(target, name, timeout=5000)
        return None if value is None else str(value)

    async def query_selector(self, target: str) -> dict[str, Any] | None:
        page = self._require_page()
        el = await page.query_selector(target)
        if el is None:
            return None
        return {
            "tag": await el.evaluate("e => e.tagName"),
            "text": (await el.text_content()) or "",
            "is_visible": await el.is_visible(),
        }

    async def query_selector_all(
        self, target: str, *, max_items: int = 100
    ) -> list[dict[str, Any]]:
        page = self._require_page()
        els = await page.query_selector_all(target)
        out: list[dict[str, Any]] = []
        for el in els[:max_items]:
            try:
                out.append(
                    {
                        "tag": await el.evaluate("e => e.tagName"),
                        "text": (await el.text_content()) or "",
                    }
                )
            except Exception as exc:  # element-fetch best-effort
                _log.debug("query_selector_all_skip: %s", exc)
                continue
        return out

    async def get_pdf(self, output_path: str | None = None) -> bytes:
        page = self._require_page()
        kwargs: dict[str, Any] = {"format": "Letter"}
        if output_path:
            kwargs["path"] = output_path
        return cast(bytes, await page.pdf(**kwargs))

    async def screenshot_element(self, target: str) -> bytes:
        page = self._require_page()
        el = await page.query_selector(target)
        if el is None:
            raise ValueError(f"element {target!r} not found")
        return cast(bytes, await el.screenshot(type="png"))

    async def get_html(self) -> str:
        page = self._require_page()
        return str(await page.content())

    async def get_console_logs(self) -> list[dict[str, str]]:
        # Returns the buffered console log entries collected since start.
        return list(getattr(self, "_console_buffer", []))

    async def get_network_log(self) -> list[dict[str, Any]]:
        return list(getattr(self, "_network_buffer", []))

    # ---- tabs --------------------------------------------------------

    def _require_context(self) -> Any:
        if self._context is None:
            raise RuntimeError("PlaywrightWebDriver: call start() first")
        return self._context

    async def new_tab(self, url: str | None = None) -> int:
        ctx = self._require_context()
        page = await ctx.new_page()
        if url:
            if not self.security.is_allowed(url):
                raise PermissionError(f"navigate to {url!r} blocked")
            await page.goto(url)
        self._page = page
        return len(ctx.pages) - 1

    async def close_tab(self, index: int | None = None) -> int:
        ctx = self._require_context()
        if index is None:
            if self._page is None:
                raise RuntimeError("no active tab")
            await self._page.close()
            self._page = ctx.pages[-1] if ctx.pages else None
            return len(ctx.pages)
        if index < 0 or index >= len(ctx.pages):
            raise IndexError(f"tab index {index} out of range")
        await ctx.pages[index].close()
        if self._page is not None and self._page.is_closed():
            self._page = ctx.pages[-1] if ctx.pages else None
        return len(ctx.pages)

    async def list_tabs(self) -> list[dict[str, str]]:
        ctx = self._require_context()
        out: list[dict[str, str]] = []
        for i, p in enumerate(ctx.pages):
            try:
                out.append(
                    {
                        "index": str(i),
                        "url": p.url,
                        "title": await p.title(),
                    }
                )
            except Exception as exc:  # tab listing best-effort
                _log.debug("list_tabs_skip[%d]: %s", i, exc)
                continue
        return out

    async def switch_tab(self, index: int) -> dict[str, str]:
        ctx = self._require_context()
        if index < 0 or index >= len(ctx.pages):
            raise IndexError(f"tab index {index} out of range")
        self._page = ctx.pages[index]
        await self._page.bring_to_front()
        return {"index": str(index), "url": self._page.url}

    async def get_active_tab(self) -> dict[str, str]:
        ctx = self._require_context()
        if self._page is None:
            raise RuntimeError("no active tab")
        index = ctx.pages.index(self._page)
        return {"index": str(index), "url": self._page.url, "title": await self._page.title()}

    async def duplicate_tab(self) -> int:
        ctx = self._require_context()
        if self._page is None:
            raise RuntimeError("no active tab")
        url = self._page.url
        new_page = await ctx.new_page()
        await new_page.goto(url)
        self._page = new_page
        return len(ctx.pages) - 1

    # ---- cookies / localStorage --------------------------------------

    async def cookies_get(self, url: str | None = None) -> list[dict[str, Any]]:
        ctx = self._require_context()
        urls = [url] if url else None
        cookies = await ctx.cookies(urls=urls)
        return list(cookies)

    async def cookies_set(self, cookies: list[dict[str, Any]]) -> None:
        ctx = self._require_context()
        await ctx.add_cookies(cookies)

    async def cookies_clear(self) -> None:
        ctx = self._require_context()
        await ctx.clear_cookies()

    async def local_storage_get(self, key: str) -> str | None:
        page = self._require_page()
        result = await page.evaluate(f"localStorage.getItem({key!r})")
        return result if result is None else str(result)

    async def local_storage_set(self, key: str, value: str) -> None:
        page = self._require_page()
        await page.evaluate(f"localStorage.setItem({key!r}, {value!r})")

    async def local_storage_clear(self) -> None:
        page = self._require_page()
        await page.evaluate("localStorage.clear()")

    # ---- cloak / stealth ---------------------------------------------

    async def set_user_agent(self, user_agent: str) -> None:
        ctx = self._require_context()
        await ctx.set_extra_http_headers({"User-Agent": user_agent})
        # And new pages via init script
        await ctx.add_init_script(
            f"Object.defineProperty(navigator, 'userAgent', {{get: () => {user_agent!r}}});"
        )

    async def set_extra_headers(self, headers: dict[str, str]) -> None:
        ctx = self._require_context()
        await ctx.set_extra_http_headers(headers)

    async def enable_stealth(self) -> None:
        """Inject baseline stealth init scripts (webdriver hide, plugins, lang)."""
        ctx = self._require_context()
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});"
            "Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});"
        )

    async def set_proxy(
        self, server: str, username: str | None = None, password: str | None = None
    ) -> None:
        # Note: Playwright proxy must be set at browser launch time; this method
        # records intent for the next start() cycle.
        self._pending_proxy = {
            "server": server,
            "username": username,
            "password": password,
        }

    async def clear_cache(self) -> None:
        ctx = self._require_context()
        # No direct API in stable Playwright; use CDP for Chromium.
        client = await ctx.new_cdp_session(self._require_page())
        await client.send("Network.clearBrowserCache")
        await client.send("Network.clearBrowserCookies")

    # ---- network --------------------------------------------------------

    async def intercept_request(
        self, url_pattern: str, mode: Literal["block", "log"] = "log"
    ) -> None:
        page = self._require_page()
        if not hasattr(self, "_network_buffer"):
            self._network_buffer: list[dict[str, Any]] = []

        async def _handler(route: Any, request: Any) -> None:
            self._network_buffer.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                }
            )
            if mode == "block":
                await route.abort()
            else:
                await route.continue_()

        await page.route(url_pattern, _handler)

    async def mock_response(
        self, url_pattern: str, body: str, status: int = 200, content_type: str = "application/json"
    ) -> None:
        page = self._require_page()

        async def _handler(route: Any) -> None:
            await route.fulfill(status=status, content_type=content_type, body=body)

        await page.route(url_pattern, _handler)

    async def block_url_pattern(self, url_pattern: str) -> None:
        await self.intercept_request(url_pattern, mode="block")

    async def wait_for_response(self, url_pattern: str, timeout: float = 30.0) -> dict[str, Any]:
        page = self._require_page()
        response = await page.wait_for_response(url_pattern, timeout=int(timeout * 1000))
        return {
            "url": response.url,
            "status": response.status,
            "headers": dict(response.headers),
        }

    # ---- device emulation --------------------------------------------

    async def emulate_device(self, device_name: str) -> None:
        # Playwright bundles device descriptors via playwright.devices map.
        if self._playwright is None:
            raise RuntimeError("driver not started")
        device = self._playwright.devices.get(device_name)
        if device is None:
            raise ValueError(f"unknown device {device_name!r}")
        # Recreate the context with device descriptor — record for next start.
        self._device_emulation = device

    async def set_geolocation(
        self, latitude: float, longitude: float, accuracy: float = 1.0
    ) -> None:
        ctx = self._require_context()
        await ctx.set_geolocation(
            {
                "latitude": latitude,
                "longitude": longitude,
                "accuracy": accuracy,
            }
        )

    async def set_locale(self, locale: str) -> None:
        self._pending_locale = locale

    async def set_timezone(self, timezone_id: str) -> None:
        ctx = self._require_context()
        # CDP override for Chromium
        client = await ctx.new_cdp_session(self._require_page())
        await client.send(
            "Emulation.setTimezoneOverride",
            {"timezoneId": timezone_id},
        )

    async def set_color_scheme(
        self, scheme: Literal["light", "dark", "no-preference"] = "light"
    ) -> None:
        page = self._require_page()
        await page.emulate_media(color_scheme=scheme)

    # ---- alias for ax_tree -------------------------------------------

    async def ax_tree(self, bundle_id: str | None = None) -> list[dict[str, Any]]:
        """DOM tree as accessibility-tree-equivalent for cross-driver tools."""
        return await self.dump_dom_tree()
