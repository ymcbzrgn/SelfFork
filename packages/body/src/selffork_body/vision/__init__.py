"""Body vision pipeline (M5 — ADR-005 §M5-B).

Gemma 4 multimodal pipeline: screenshot → preprocess → prompt → tier-1/2/3
fallback → JSON action decision. Drives the cross-UI control loops in
``selffork_body.drivers``.

Public surface:

* :class:`ScreenshotCapture` Protocol + factory dispatch.
* :func:`preprocess` and :func:`delta_image` for image normalisation.
* :func:`build_prompt` and :func:`parse_decision` for LLM I/O.
* :class:`VisionOrchestrator` — tier orchestration and audit emit.
* :class:`MlxVlmAdapter` and :class:`OllamaVisionAdapter` runtime adapters.
* :class:`LatencyTracker` for cockpit gauges.
"""

from __future__ import annotations

from selffork_body.vision.preprocess import (
    PreprocessConfig,
    TokenBudget,
    delta_image,
    preprocess,
)
from selffork_body.vision.profiling import LatencyBreakdown, LatencyTracker
from selffork_body.vision.prompt import Tier, build_prompt, parse_decision
from selffork_body.vision.runtime import (
    MlxVlmAdapter,
    OllamaVisionAdapter,
    VisionDecision,
    VisionOrchestrator,
)
from selffork_body.vision.screenshot import (
    AndroidScreenshotCapture,
    DriverKind,
    IosSimulatorScreenshotCapture,
    LinuxScreenshotCapture,
    MacOSScreenshotCapture,
    ScreenshotCapture,
    detect_driver,
    get_screenshot_capture,
)

__all__ = [
    "AndroidScreenshotCapture",
    "DriverKind",
    "IosSimulatorScreenshotCapture",
    "LatencyBreakdown",
    "LatencyTracker",
    "LinuxScreenshotCapture",
    "MacOSScreenshotCapture",
    "MlxVlmAdapter",
    "OllamaVisionAdapter",
    "PreprocessConfig",
    "ScreenshotCapture",
    "Tier",
    "TokenBudget",
    "VisionDecision",
    "VisionOrchestrator",
    "build_prompt",
    "delta_image",
    "detect_driver",
    "get_screenshot_capture",
    "parse_decision",
    "preprocess",
]
