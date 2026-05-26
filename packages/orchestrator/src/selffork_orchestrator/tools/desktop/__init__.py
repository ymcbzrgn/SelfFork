"""Desktop tool pack — macOS (cua-style background driver) (~15 tools).

S-ToolFleet Faz 3. Built on
:class:`selffork_body.drivers.desktop.macos.driver.MacOSDesktopDriver`
(extended in Faz 3 with double_click/right_click/screenshot_region/
get_active_app/list_apps/list_windows/focus_window/get_clipboard/
set_clipboard/notification/say).

Naming convention: every tool starts with ``desktop_*``. The eager
bucket = top-5 (click/type/screenshot/press_key/get_active_app) — the
canonical desktop observe→act loop. Remaining ~10 defer behind
``tool_search``.

Reference: cua (MIT) — background non-focus macOS driver pattern.
Skyvern AGPL avoided; AppleScript + pyobjc-quartz native stack only.
"""

from __future__ import annotations

from typing import Any

from selffork_orchestrator.tools.base import ToolSpec
from selffork_orchestrator.tools.desktop.tools import build_desktop_tools_inner

__all__ = ["build_desktop_tools"]


def build_desktop_tools() -> list[ToolSpec[Any]]:
    """Return every macOS desktop tool in canonical ordering."""
    return build_desktop_tools_inner()
