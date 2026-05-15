"""TCC permission probes (M5 — ADR-005 §M5-C4).

macOS protects Accessibility, Screen Recording, and Input Monitoring behind
TCC (Transparency, Consent, and Control). The body driver needs both
Accessibility and Screen Recording grants on first run; these helpers let
the daemon installer surface a friendly prompt when missing.
"""

from __future__ import annotations

import sys

__all__ = [
    "check_accessibility_permission",
    "check_screen_recording_permission",
]


def _macos_or_false() -> bool:
    return sys.platform == "darwin"


async def check_accessibility_permission() -> bool:
    """Return True when the current process holds Accessibility permission."""
    if not _macos_or_false():
        return False
    try:
        from ApplicationServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except ImportError:  # pragma: no cover
        return False


async def check_screen_recording_permission() -> bool:
    """Best-effort Screen Recording probe via CGWindowListCreateImage.

    macOS doesn't expose a clean "do I have screen recording?" API; the
    convention is to attempt an off-screen capture and fall back when the
    image is empty (signal that TCC redacted it).
    """
    if not _macos_or_false():
        return False
    try:
        from Quartz import (
            CGRectMake,
            CGWindowListCreateImage,
            kCGNullWindowID,
            kCGWindowImageDefault,
            kCGWindowListOptionOnScreenOnly,
        )
    except ImportError:  # pragma: no cover
        return False
    image = CGWindowListCreateImage(
        CGRectMake(0, 0, 1, 1),
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
        kCGWindowImageDefault,
    )
    return image is not None
