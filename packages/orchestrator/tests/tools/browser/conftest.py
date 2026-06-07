"""Shared stub browser driver + fixtures for browser tool tests."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from selffork_body.sandbox import PermissionWarden, WardenMode
from selffork_orchestrator.tools.base import ToolContext


class _StubProjectStore:
    pass


@dataclass
class StubBrowserDriver:
    """Stub matching the PlaywrightWebDriver duck-typed surface (Faz 2)."""

    platform: str = "web"
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)

    def _record(self, name: str, args: tuple, kwargs: dict) -> None:
        self.calls.append((name, args, dict(kwargs)))

    # ---- core (M5) -----------------------------------------------------

    async def start(self) -> None:
        self._record("start", (), {})

    async def stop(self) -> None:
        self._record("stop", (), {})

    async def goto(self, url: str) -> None:
        self._record("goto", (url,), {})

    async def click(self, target, bbox=None, button="left"):
        self._record("click", (target,), {"bbox": bbox, "button": button})

    async def type_text(self, text, target=None):
        self._record("type_text", (text,), {"target": target})

    async def screenshot(self, rect=None):
        self._record("screenshot", (), {"rect": rect})
        return b"\x89PNG\r\n\x1a\nSTUB"

    async def scroll(self, direction="down", amount=300):
        self._record("scroll", (), {"direction": direction, "amount": amount})

    async def press_key(self, key_combo):
        self._record("press_key", (key_combo,), {})

    async def wait_for(self, selector, timeout=5.0):  # noqa: ASYNC109
        self._record("wait_for", (selector,), {"timeout": timeout})

    async def evaluate(self, js_code):
        self._record("evaluate", (js_code,), {})
        return {"result": "stub"}

    async def dump_dom_tree(self):
        self._record("dump_dom_tree", (), {})
        return [
            {"tag": "button", "text": "Submit", "role": "button"},
            {"tag": "input", "text": "", "role": "textbox"},
            {"tag": "div", "text": "Welcome to SelfFork"},
        ]

    async def storage_state_save(self, provider=None, project_slug=None):
        self._record("storage_state_save", (provider,), {"project_slug": project_slug})
        from pathlib import Path

        return Path("/tmp/state.json")

    async def storage_state_load(self, provider=None, project_slug=None):
        self._record("storage_state_load", (provider,), {"project_slug": project_slug})
        return True

    # ---- Faz 2 extensions ---------------------------------------------

    async def double_click(self, target=None, *, x=None, y=None, button="left"):
        self._record("double_click", (target,), {"x": x, "y": y, "button": button})

    async def hover(self, target=None, *, x=None, y=None):
        self._record("hover", (target,), {"x": x, "y": y})

    async def fill_form(self, fields):
        self._record("fill_form", (), {"field_count": len(fields)})
        return len(fields)

    async def select_option(self, target, value=None, *, label=None, index=None):
        self._record("select_option", (target,), {"value": value, "label": label, "index": index})
        return [str(value) if value else (label or str(index))]

    async def check(self, target):
        self._record("check", (target,), {})

    async def uncheck(self, target):
        self._record("uncheck", (target,), {})

    async def drag_and_drop(self, source, target):
        self._record("drag_and_drop", (source, target), {})

    async def upload_file(self, target, file_path):
        self._record("upload_file", (target,), {"file_path": file_path})

    async def clear(self, target):
        self._record("clear", (target,), {})

    async def swipe(self, sx, sy, ex, ey, duration_ms=250):
        self._record("swipe", (sx, sy, ex, ey), {"duration_ms": duration_ms})

    async def back(self):
        self._record("back", (), {})

    async def forward(self):
        self._record("forward", (), {})

    async def reload(self):
        self._record("reload", (), {})

    async def get_url(self):
        self._record("get_url", (), {})
        return "https://selffork.dev"

    async def get_title(self):
        self._record("get_title", (), {})
        return "SelfFork"

    async def set_viewport(self, w, h):
        self._record("set_viewport", (w, h), {})

    async def wait_for_load_state(self, state="load", timeout=30.0):  # noqa: ASYNC109
        self._record("wait_for_load_state", (state,), {"timeout": timeout})

    async def wait_for_url(self, url_pattern, timeout=30.0):  # noqa: ASYNC109
        self._record("wait_for_url", (url_pattern,), {"timeout": timeout})

    async def text_content(self, target):
        self._record("text_content", (target,), {})
        return "Hello"

    async def get_attribute(self, target, name):
        self._record("get_attribute", (target, name), {})
        return "attr_value"

    async def query_selector(self, target):
        self._record("query_selector", (target,), {})
        return {"tag": "BUTTON", "text": "Submit", "is_visible": True}

    async def query_selector_all(self, target, *, max_items=100):
        self._record("query_selector_all", (target,), {"max_items": max_items})
        return [{"tag": "DIV", "text": "x"}]

    async def get_pdf(self, output_path=None):
        self._record("get_pdf", (output_path,), {})
        return b"%PDF-1.7\nstub"

    async def screenshot_element(self, target):
        self._record("screenshot_element", (target,), {})
        return b"\x89PNG\r\n\x1a\nELEM"

    async def get_html(self):
        self._record("get_html", (), {})
        return "<html><body>SelfFork</body></html>"

    async def get_console_logs(self):
        self._record("get_console_logs", (), {})
        return [{"level": "log", "text": "ready"}]

    async def get_network_log(self):
        self._record("get_network_log", (), {})
        return [{"url": "https://x", "method": "GET", "status": 200}]

    async def new_tab(self, url=None):
        self._record("new_tab", (url,), {})
        return 1

    async def close_tab(self, index=None):
        self._record("close_tab", (index,), {})
        return 0

    async def list_tabs(self):
        self._record("list_tabs", (), {})
        return [{"index": "0", "url": "https://x", "title": "X"}]

    async def switch_tab(self, index):
        self._record("switch_tab", (index,), {})
        return {"index": str(index), "url": "https://x"}

    async def get_active_tab(self):
        self._record("get_active_tab", (), {})
        return {"index": "0", "url": "https://x", "title": "X"}

    async def duplicate_tab(self):
        self._record("duplicate_tab", (), {})
        return 1

    async def cookies_get(self, url=None):
        self._record("cookies_get", (url,), {})
        return [{"name": "session", "value": "abc"}]

    async def cookies_set(self, cookies):
        self._record("cookies_set", (), {"count": len(cookies)})

    async def cookies_clear(self):
        self._record("cookies_clear", (), {})

    async def local_storage_get(self, key):
        self._record("local_storage_get", (key,), {})
        return "stored"

    async def local_storage_set(self, key, value):
        self._record("local_storage_set", (key, value), {})

    async def local_storage_clear(self):
        self._record("local_storage_clear", (), {})

    async def set_user_agent(self, ua):
        self._record("set_user_agent", (ua,), {})

    async def set_extra_headers(self, headers):
        self._record("set_extra_headers", (), {"count": len(headers)})

    async def enable_stealth(self):
        self._record("enable_stealth", (), {})

    async def set_proxy(self, server, username=None, password=None):
        self._record("set_proxy", (server,), {"username": username})

    async def clear_cache(self):
        self._record("clear_cache", (), {})

    async def intercept_request(self, url_pattern, mode="log"):
        self._record("intercept_request", (url_pattern,), {"mode": mode})

    async def mock_response(self, url_pattern, body, status=200, content_type="application/json"):
        self._record("mock_response", (url_pattern,), {"status": status})

    async def block_url_pattern(self, url_pattern):
        self._record("block_url_pattern", (url_pattern,), {})

    async def wait_for_response(self, url_pattern, timeout=30.0):  # noqa: ASYNC109
        self._record("wait_for_response", (url_pattern,), {"timeout": timeout})
        return {"url": url_pattern, "status": 200, "headers": {}}

    async def emulate_device(self, device_name):
        self._record("emulate_device", (device_name,), {})

    async def set_geolocation(self, lat, lon, accuracy=1.0):
        self._record("set_geolocation", (lat, lon), {"accuracy": accuracy})

    async def set_locale(self, locale):
        self._record("set_locale", (locale,), {})

    async def set_timezone(self, tz):
        self._record("set_timezone", (tz,), {})

    async def set_color_scheme(self, scheme="light"):
        self._record("set_color_scheme", (scheme,), {})

    async def ax_tree(self, bundle_id=None):
        self._record("ax_tree", (), {})
        return await self.dump_dom_tree()


def make_ctx(
    *,
    driver=None,
    warden=None,
    vision_runtime=None,
    screenshot_store=None,
    session_id="sess-test",
    project_slug=None,
) -> ToolContext:
    if warden is None and driver is not None:
        warden = PermissionWarden(mode=WardenMode.DANGER_FULL_ACCESS)
    return ToolContext(
        session_id=session_id,
        project_slug=project_slug,
        project_store=_StubProjectStore(),
        body_driver=driver,
        permission_warden=warden,
        vision_runtime=vision_runtime,
        screenshot_store=screenshot_store,
    )


@pytest.fixture
def stub_browser_driver() -> StubBrowserDriver:
    return StubBrowserDriver()


@pytest.fixture
def ctx_browser(stub_browser_driver) -> ToolContext:
    return make_ctx(driver=stub_browser_driver)


@pytest.fixture
def ctx_no_browser() -> ToolContext:
    return make_ctx(driver=None)
