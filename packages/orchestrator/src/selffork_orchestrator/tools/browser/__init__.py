"""Browser tool fleet — Playwright + browser-use + stagehand patterns (~60 tools).

S-ToolFleet Faz 2 Browser Wave. Built on top of
:class:`selffork_body.drivers.web.playwright_driver.PlaywrightWebDriver`
(extended in Faz 2 with ~35 new methods covering interaction, navigation,
observation, tabs, cookies/localStorage, cloak/stealth, network
interception and device emulation).

Naming convention: every tool starts with ``browser_*``. Eager bucket =
top-10 (navigate/click/type/screenshot/dom_snapshot/text_content/evaluate/
press_key/wait_for/get_url) — the canonical agentic browser loop. The
remaining ~50 defer behind ``tool_search``.

Adopt references (license respect):

* browser-use (MIT) — registry-decorator pattern + per-action timeout
* stagehand (MIT) — act/extract/observe/agent 4-method shape
* CloakBrowser (MIT) — humanize=True + stealth init scripts
* skyvern (AGPL) — *fikir-only*, no code copied
"""

from __future__ import annotations

from typing import Any

from selffork_orchestrator.tools.base import ToolSpec
from selffork_orchestrator.tools.browser.cloak import build_browser_cloak_tools
from selffork_orchestrator.tools.browser.device import build_browser_device_tools
from selffork_orchestrator.tools.browser.intelligent import (
    build_browser_intelligent_tools,
)
from selffork_orchestrator.tools.browser.interaction import (
    build_browser_interaction_tools,
)
from selffork_orchestrator.tools.browser.navigation import build_browser_navigation_tools
from selffork_orchestrator.tools.browser.network import build_browser_network_tools
from selffork_orchestrator.tools.browser.observation import (
    build_browser_observation_tools,
)
from selffork_orchestrator.tools.browser.storage import build_browser_storage_tools
from selffork_orchestrator.tools.browser.tabs import build_browser_tabs_tools

__all__ = [
    "build_browser_cloak_tools",
    "build_browser_device_tools",
    "build_browser_intelligent_tools",
    "build_browser_interaction_tools",
    "build_browser_navigation_tools",
    "build_browser_network_tools",
    "build_browser_observation_tools",
    "build_browser_storage_tools",
    "build_browser_tabs_tools",
    "build_browser_tools",
]


def build_browser_tools() -> list[ToolSpec[Any]]:
    """Return every browser tool in canonical ordering (interaction first)."""
    specs: list[ToolSpec[Any]] = []
    specs.extend(build_browser_navigation_tools())  # navigation eager (get_url, navigate)
    specs.extend(build_browser_interaction_tools())  # interaction eager core
    specs.extend(build_browser_observation_tools())  # observation eager core
    specs.extend(build_browser_tabs_tools())
    specs.extend(build_browser_storage_tools())
    specs.extend(build_browser_intelligent_tools())
    specs.extend(build_browser_cloak_tools())
    specs.extend(build_browser_network_tools())
    specs.extend(build_browser_device_tools())
    return specs
