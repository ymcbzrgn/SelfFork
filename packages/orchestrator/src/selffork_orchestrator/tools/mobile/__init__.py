"""Mobile tool fleet — iOS + Android + Expo + UI-verify + crash/state.

S-ToolFleet Faz 1 — Mobile Wave (~120 tools). Built on top of the
existing :class:`selffork_body.drivers.ios.IosDriver` and
:class:`selffork_body.drivers.android.AndroidDriver` plus
:class:`selffork_body.drivers.mobile_factory.CompositeMobileDriver`.

Naming convention:

* ``ios_*`` — iOS-only operations (Simulator + Appium XCUITest)
* ``android_*`` — Android-only operations (docker-android + mobile-mcp
  + uiautomator2 + raw ADB)
* ``expo_*`` — Expo dev workflow (subprocess wrapper around ``expo``/
  ``eas`` CLIs)
* ``ui_verify_*`` — A11y + OCR + visual assertions (eager — observe
  loop dependency)
* ``crash_*`` — crash log / bug report / state snapshot+restore for
  autonomous regression

Defer policy (per ADR-010 §9.3): top-10 per platform + every
``ui_verify_*`` are eager (defer_loading=False) so Self Jr always sees
the canonical mobile loop. Deep / specialised tools (~80) defer; the
``tool_search`` meta-tool retrieves them on demand.
"""

from __future__ import annotations

from typing import Any

from selffork_orchestrator.tools.base import ToolSpec
from selffork_orchestrator.tools.mobile.android import build_android_tools
from selffork_orchestrator.tools.mobile.crash_state import build_crash_state_tools
from selffork_orchestrator.tools.mobile.expo import build_expo_tools
from selffork_orchestrator.tools.mobile.ios import build_ios_tools
from selffork_orchestrator.tools.mobile.ui_verify import build_ui_verify_tools

__all__ = [
    "build_android_tools",
    "build_crash_state_tools",
    "build_expo_tools",
    "build_ios_tools",
    "build_mobile_tools",
    "build_ui_verify_tools",
]


def build_mobile_tools() -> list[ToolSpec[Any]]:
    """Return the full mobile-wave tool catalog in canonical ordering.

    Ordering matters for the eager system-prompt slice (deferred tools
    fall after the eager group implicitly through ``defer_loading``).
    iOS first then Android mirrors the operator's daily-driver split
    (Expo on macOS → iOS Simulator).
    """
    specs: list[ToolSpec[Any]] = []
    specs.extend(build_ios_tools())
    specs.extend(build_android_tools())
    specs.extend(build_ui_verify_tools())
    specs.extend(build_expo_tools())
    specs.extend(build_crash_state_tools())
    return specs
