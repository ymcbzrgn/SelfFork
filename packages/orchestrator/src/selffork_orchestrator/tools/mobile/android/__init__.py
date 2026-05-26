"""Android tool pack — mobile-mcp + uiautomator2 + ADB surface (~45 tools).

S-ToolFleet Faz 1. Splits by concern:

* :mod:`interaction` — click/type/swipe/scroll/long-press/double-click/
  clear-text/pinch/press-key (9 tools)
* :mod:`observation` — screenshot/ax_tree/screen_text (3 tools)
* :mod:`lifecycle` — launch/terminate/force_stop/clear_data/install/
  uninstall/list/activate (8 tools)
* :mod:`system` — orientation/clipboard/property/reboot/battery/
  app_state/screen_size (8 tools)
* :mod:`intent` — intent/broadcast/deeplink/press_button/notification (5 tools)
* :mod:`shell` — shell/pull/push/logcat/dumpsys/screenrecord_start/
  screenrecord_stop/install_xapk (8 tools)
* :mod:`emulator` — device_list/set_geolocation/emulator_boot/
  emulator_shutdown (4 tools)
"""

from __future__ import annotations

from typing import Any

from selffork_orchestrator.tools.base import ToolSpec
from selffork_orchestrator.tools.mobile.android.emulator import build_android_emulator_tools
from selffork_orchestrator.tools.mobile.android.intent import build_android_intent_tools
from selffork_orchestrator.tools.mobile.android.interaction import (
    build_android_interaction_tools,
)
from selffork_orchestrator.tools.mobile.android.lifecycle import (
    build_android_lifecycle_tools,
)
from selffork_orchestrator.tools.mobile.android.observation import (
    build_android_observation_tools,
)
from selffork_orchestrator.tools.mobile.android.shell import build_android_shell_tools
from selffork_orchestrator.tools.mobile.android.system import build_android_system_tools

__all__ = [
    "build_android_emulator_tools",
    "build_android_intent_tools",
    "build_android_interaction_tools",
    "build_android_lifecycle_tools",
    "build_android_observation_tools",
    "build_android_shell_tools",
    "build_android_system_tools",
    "build_android_tools",
]


def build_android_tools() -> list[ToolSpec[Any]]:
    """Return every Android tool in canonical ordering."""
    specs: list[ToolSpec[Any]] = []
    specs.extend(build_android_interaction_tools())
    specs.extend(build_android_observation_tools())
    specs.extend(build_android_lifecycle_tools())
    specs.extend(build_android_system_tools())
    specs.extend(build_android_intent_tools())
    specs.extend(build_android_shell_tools())
    specs.extend(build_android_emulator_tools())
    return specs
