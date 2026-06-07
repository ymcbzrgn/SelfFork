"""Shared stubs + fixtures for Faz 3 tests (desktop / github / skills)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from selffork_body.sandbox import PermissionWarden, WardenMode
from selffork_orchestrator.tools.base import ToolContext


class _StubProjectStore:
    pass


@dataclass
class StubMacosDriver:
    """Duck-typed MacOSDesktopDriver stub for handler dispatch."""

    platform: str = "macos"
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)

    def _record(self, name: str, args: tuple, kwargs: dict) -> None:
        self.calls.append((name, args, dict(kwargs)))

    async def start(self) -> None:
        self._record("start", (), {})

    async def stop(self) -> None:
        self._record("stop", (), {})

    async def click(self, target, bbox=None, button="left"):
        self._record("click", (target,), {"bbox": bbox, "button": button})

    async def double_click(self, x, y):
        self._record("double_click", (x, y), {})

    async def right_click(self, x, y):
        self._record("right_click", (x, y), {})

    async def type_text(self, text, target=None):
        self._record("type_text", (text,), {"target": target})

    async def press_key(self, key_combo):
        self._record("press_key", (key_combo,), {})

    async def screenshot(self, rect=None):
        self._record("screenshot", (), {"rect": rect})
        return b"\x89PNG\r\n\x1a\nSTUB"

    async def screenshot_region(self, x, y, w, h):
        self._record("screenshot_region", (x, y, w, h), {})
        return b"\x89PNG\r\n\x1a\nREGION"

    async def get_active_app(self):
        self._record("get_active_app", (), {})
        return {"name": "Terminal", "bundleId": "com.apple.Terminal"}

    async def list_apps(self):
        self._record("list_apps", (), {})
        return [{"name": "Terminal", "bundleId": "com.apple.Terminal"}]

    async def list_windows(self, app_name=None):
        self._record("list_windows", (app_name,), {})
        return [{"app": "Terminal", "title": "bash"}]

    async def focus_window(self, app_name, window_title=None):
        self._record("focus_window", (app_name, window_title), {})

    async def get_clipboard(self):
        self._record("get_clipboard", (), {})
        return "clip"

    async def set_clipboard(self, text):
        self._record("set_clipboard", (text,), {})

    async def notification(self, title, body, subtitle=None):
        self._record("notification", (title, body, subtitle), {})

    async def say(self, text, voice=None, rate=None):
        self._record("say", (text,), {"voice": voice, "rate": rate})


def make_ctx(
    *,
    driver=None,
    warden=None,
    audit_logger=None,
    screenshot_store=None,
    session_id="sess-test",
    project_slug=None,
) -> ToolContext:
    if warden is None:
        warden = PermissionWarden(mode=WardenMode.DANGER_FULL_ACCESS)
    return ToolContext(
        session_id=session_id,
        project_slug=project_slug,
        project_store=_StubProjectStore(),
        body_driver=driver,
        permission_warden=warden,
        audit_logger=audit_logger,
        screenshot_store=screenshot_store,
    )


@pytest.fixture
def stub_macos_driver() -> StubMacosDriver:
    return StubMacosDriver()


@pytest.fixture
def ctx_macos(stub_macos_driver) -> ToolContext:
    return make_ctx(driver=stub_macos_driver)


@pytest.fixture
def ctx_no_driver_with_warden() -> ToolContext:
    """GitHub + skills tools don't need a driver; warden alone enough."""
    return make_ctx(driver=None)
