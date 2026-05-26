"""VR/AR tool fleet — Quest 3 (Android-derived) + Vision Pro (vision-only).

S-ToolFleet Faz 4 per ADR-010 §9.1 #3 operator lock + §9.3 5-Faz plan:

* **Quest 3 (17 tools)** — full driver on top of Android base. Reuses
  ``android_*`` for click/swipe/screenshot/install/etc.; adds VR-specific
  ``quest_*`` ops for recenter, passthrough, controller buttons,
  battery, boundary, voice.
* **Vision Pro (8 tools)** — vision-only OCR fallback. visionOS XCTest
  + Appium NOT available; ships screenshot + xcrun simctl + AppleScript
  pointer + LLM-driven text finding.

Modalite-çift kabul: honest about the visionOS reality. ~25 tools total.
"""

from __future__ import annotations

from typing import Any

from selffork_orchestrator.tools.base import ToolSpec
from selffork_orchestrator.tools.vr.quest import build_quest_tools
from selffork_orchestrator.tools.vr.visionpro import build_visionpro_tools

__all__ = [
    "build_quest_tools",
    "build_visionpro_tools",
    "build_vr_tools",
]


def build_vr_tools() -> list[ToolSpec[Any]]:
    """Return every VR/AR tool in canonical ordering (Quest first)."""
    specs: list[ToolSpec[Any]] = []
    specs.extend(build_quest_tools())
    specs.extend(build_visionpro_tools())
    return specs
