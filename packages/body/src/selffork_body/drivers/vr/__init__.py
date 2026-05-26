"""VR/AR drivers — Quest 3 (Android-derived) + Vision Pro (visionOS).

S-ToolFleet Faz 4. Per ADR-010 §9.1 #3 operator lock:

* **Quest 3** — Android ADB+MQDH full driver (~17 tools). Inherits from
  :class:`AndroidDriver` since Quest OS is Android-derived; adds VR-specific
  intents (recenter, passthrough, controller buttons, battery, boundary).
* **Vision Pro** — Gemma 4 VLM OCR vision-only (~8 tools). visionOS XCTest is
  "Designed for iPad" sınırlı; Appium yok. So screenshot + xcrun simctl
  + AppleScript pointer + LLM-driven OCR.

Modalite-çift kabul: Quest gets the full driver, Vision Pro gets the
vision-only fallback. Honest reality, not equal effort.
"""

from __future__ import annotations

from selffork_body.drivers.vr.quest import QuestDriver
from selffork_body.drivers.vr.visionpro import VisionProDriver

__all__ = ["QuestDriver", "VisionProDriver"]
