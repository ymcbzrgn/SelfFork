"""Web driver public surface (M5 — ADR-005 §M5-C1).

Stack: Playwright + Chromium primary; vision fallback layered via
:class:`selffork_body.vision.VisionOrchestrator`. ``Stagehand v3`` adapter
deferred per R4 vendor-test gate (M5 §M5-C1 sub-task 5.5).
"""

from __future__ import annotations

from selffork_body.drivers.web.dom_extractor import (
    DOM_TREE_JS,
    extract_dom_tree,
    summarise_dom_tree,
)
from selffork_body.drivers.web.playwright_driver import PlaywrightWebDriver
from selffork_body.drivers.web.security_watchdog import SecurityWatchdog
from selffork_body.drivers.web.storage_state import (
    StorageStateAutoSave,
    WebStorageStateManager,
)

__all__ = [
    "DOM_TREE_JS",
    "PlaywrightWebDriver",
    "SecurityWatchdog",
    "StorageStateAutoSave",
    "WebStorageStateManager",
    "extract_dom_tree",
    "summarise_dom_tree",
]
