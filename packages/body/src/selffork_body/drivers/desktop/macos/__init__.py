"""macOS desktop driver (M5 — ADR-005 §M5-C4).

Native AX-tree primary + screencapture screenshot fallback + AppleScript
runner. PyObjC + ApplicationServices framework are imported lazily so the
module can be imported on non-Darwin hosts for unit testing.
"""

from __future__ import annotations

from selffork_body.drivers.desktop.macos.applescript_runner import AppleScriptRunner
from selffork_body.drivers.desktop.macos.driver import MacOSDesktopDriver
from selffork_body.drivers.desktop.macos.pyobjc_ax_driver import (
    AxElementSummary,
    MacOSAxDriver,
)
from selffork_body.drivers.desktop.macos.screencapture import MacOSScreencaptureCapture
from selffork_body.drivers.desktop.macos.tcc_check import (
    check_accessibility_permission,
    check_screen_recording_permission,
)

__all__ = [
    "AppleScriptRunner",
    "AxElementSummary",
    "MacOSAxDriver",
    "MacOSDesktopDriver",
    "MacOSScreencaptureCapture",
    "check_accessibility_permission",
    "check_screen_recording_permission",
]
