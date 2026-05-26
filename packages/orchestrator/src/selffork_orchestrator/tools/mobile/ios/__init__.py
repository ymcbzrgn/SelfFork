"""iOS tool pack — Simulator + Appium XCUITest surface (~45 tools).

S-ToolFleet Faz 1. Splits by concern:

* :mod:`interaction` — click/type/swipe/scroll/long-press/double-click/
  clear-text/pinch/press-key (9 tools)
* :mod:`observation` — screenshot/ax_tree/screen_text (3 tools)
* :mod:`lifecycle` — launch/terminate/activate/state/install/uninstall/
  background/list_apps (8 tools)
* :mod:`system` — orientation/clipboard/lock/unlock/terminate_keyboard/
  press_button (8 tools)
* :mod:`simulator` — list/boot/shutdown/erase/biometric/logs/push/
  status_bar/appearance (10 tools)
* :mod:`network` — open_url/geolocation/record_video (5 tools)
* :mod:`element` — find/active (2 tools)

Eager bucket (defer_loading=False) = 10 tools (top of each concern that
the agentic mobile loop needs every observe→act cycle). Remaining ~35
defer behind ``tool_search``.
"""

from __future__ import annotations

from typing import Any

from selffork_orchestrator.tools.base import ToolSpec
from selffork_orchestrator.tools.mobile.ios.element import build_ios_element_tools
from selffork_orchestrator.tools.mobile.ios.interaction import build_ios_interaction_tools
from selffork_orchestrator.tools.mobile.ios.lifecycle import build_ios_lifecycle_tools
from selffork_orchestrator.tools.mobile.ios.network import build_ios_network_tools
from selffork_orchestrator.tools.mobile.ios.observation import build_ios_observation_tools
from selffork_orchestrator.tools.mobile.ios.simulator import build_ios_simulator_tools
from selffork_orchestrator.tools.mobile.ios.system import build_ios_system_tools

__all__ = [
    "build_ios_element_tools",
    "build_ios_interaction_tools",
    "build_ios_lifecycle_tools",
    "build_ios_network_tools",
    "build_ios_observation_tools",
    "build_ios_simulator_tools",
    "build_ios_system_tools",
    "build_ios_tools",
]


def build_ios_tools() -> list[ToolSpec[Any]]:
    """Return every iOS-DEEP tool in canonical ordering."""
    specs: list[ToolSpec[Any]] = []
    specs.extend(build_ios_interaction_tools())
    specs.extend(build_ios_observation_tools())
    specs.extend(build_ios_lifecycle_tools())
    specs.extend(build_ios_system_tools())
    specs.extend(build_ios_simulator_tools())
    specs.extend(build_ios_network_tools())
    specs.extend(build_ios_element_tools())
    return specs
