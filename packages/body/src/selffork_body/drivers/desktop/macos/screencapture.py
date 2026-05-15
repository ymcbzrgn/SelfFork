"""macOS ``screencapture`` PNG capture wrapper.

Re-exports the ``MacOSScreenshotCapture`` from the vision package so the
driver namespace stays self-contained without source duplication.
"""

from __future__ import annotations

from selffork_body.vision.screenshot import MacOSScreenshotCapture

__all__ = ["MacOSScreencaptureCapture"]


class MacOSScreencaptureCapture(MacOSScreenshotCapture):
    """Marker subclass to make the driver-side API explicit."""
