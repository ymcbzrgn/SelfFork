"""Unified macOS desktop driver (M5 — ADR-005 §M5-C4).

Composes:

* :class:`MacOSAxDriver` for AX-tree primary path (label match, AXPress).
* :class:`MacOSScreencaptureCapture` for screenshot.
* :class:`AppleScriptRunner` for app lifecycle (launch/activate/quit).

Vision fallback is layered above the driver in
:class:`selffork_body.vision.VisionOrchestrator` — when the AX tree doesn't
resolve a label, the caller renders a screenshot, asks the LLM, and converts
the response to a coordinate ``click(x, y)``.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Literal

from selffork_body.drivers.desktop.macos.applescript_runner import AppleScriptRunner
from selffork_body.drivers.desktop.macos.pyobjc_ax_driver import MacOSAxDriver
from selffork_body.drivers.desktop.macos.screencapture import MacOSScreencaptureCapture

__all__ = ["MacOSDesktopDriver"]


class MacOSDesktopDriver:
    def __init__(
        self,
        *,
        ax: MacOSAxDriver | None = None,
        screencapture: MacOSScreencaptureCapture | None = None,
        applescript: AppleScriptRunner | None = None,
    ) -> None:
        self._ax = ax or MacOSAxDriver()
        self._screencapture = screencapture or MacOSScreencaptureCapture()
        self._applescript = applescript or AppleScriptRunner()

    async def start(self) -> None:
        # Lazy — Quartz / AX state initialised on first use.
        return

    async def stop(self) -> None:
        return

    async def click(
        self,
        target: str | int,
        bbox: tuple[int, int, int, int] | None = None,
        button: Literal["left", "right"] = "left",
    ) -> None:
        if isinstance(target, int) and bbox is None:
            raise ValueError("integer target requires bbox")
        if bbox is not None:
            cx = bbox[0] + bbox[2] // 2
            cy = bbox[1] + bbox[3] // 2
            await self._post_mouse_click(cx, cy, button)
            return
        # Try AX label match across all visible apps when no bbox is given.
        # This is best-effort — production callers prefer to resolve the
        # element via vision/AX-summarise first and pass an explicit bbox.
        raise NotImplementedError(
            "MacOSDesktopDriver.click without bbox requires VisionOrchestrator; "
            "pass bbox=(x,y,w,h) or wire a vision fallback above the driver."
        )

    async def _post_mouse_click(self, x: int, y: int, button: str) -> None:
        if sys.platform != "darwin":  # pragma: no cover - ci guard
            raise RuntimeError("mouse click requires Darwin")
        from Quartz import (
            CGEventCreateMouseEvent,
            CGEventPost,
            kCGEventLeftMouseDown,
            kCGEventLeftMouseUp,
            kCGEventRightMouseDown,
            kCGEventRightMouseUp,
            kCGHIDEventTap,
            kCGMouseButtonLeft,
            kCGMouseButtonRight,
        )

        if button == "left":
            down = kCGEventLeftMouseDown
            up = kCGEventLeftMouseUp
            btn = kCGMouseButtonLeft
        else:
            down = kCGEventRightMouseDown
            up = kCGEventRightMouseUp
            btn = kCGMouseButtonRight
        loc = (x, y)
        await asyncio.to_thread(
            CGEventPost, kCGHIDEventTap, CGEventCreateMouseEvent(None, down, loc, btn)
        )
        await asyncio.to_thread(
            CGEventPost, kCGHIDEventTap, CGEventCreateMouseEvent(None, up, loc, btn)
        )

    async def type_text(self, text: str, target: str | None = None) -> None:
        # Use AppleScript "keystroke" — reliable for short text. For huge
        # paste-style input use NSPasteboard + Cmd+V (M6 enhancement).
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'Application("System Events").keystroke("{escaped}");'
        await self._applescript.run(script)

    async def screenshot(self, rect: tuple[int, int, int, int] | None = None) -> bytes:
        return await self._screencapture.capture(rect)

    async def scroll(self, direction: str = "down", amount: int = 300) -> None:
        if sys.platform != "darwin":  # pragma: no cover
            raise RuntimeError("scroll requires Darwin")
        from Quartz import (
            CGEventCreateScrollWheelEvent,
            CGEventPost,
            kCGHIDEventTap,
            kCGScrollEventUnitPixel,
        )

        dx, dy = 0, 0
        if direction == "down":
            dy = -amount
        elif direction == "up":
            dy = amount
        elif direction == "left":
            dx = -amount
        elif direction == "right":
            dx = amount
        else:
            raise ValueError(f"unsupported scroll direction {direction!r}")
        await asyncio.to_thread(
            CGEventPost,
            kCGHIDEventTap,
            CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitPixel, 2, dy, dx),
        )

    async def swipe(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        raise NotImplementedError("desktop driver does not expose swipe; use scroll")

    async def app_launch(self, bundle_id: str) -> None:
        await self._applescript.app_launch(bundle_id)

    async def press_key(self, key_combo: str) -> None:
        # Translate "cmd+t" → AppleScript "keystroke t using {command down}".
        parts = [p.strip() for p in key_combo.split("+") if p.strip()]
        if not parts:
            raise ValueError("empty key combo")
        modifiers = []
        key = parts[-1]
        for mod in parts[:-1]:
            mod_map = {
                "cmd": "command", "command": "command",
                "ctrl": "control", "control": "control",
                "alt": "option", "option": "option",
                "shift": "shift",
            }
            mod_clean = mod_map.get(mod.lower())
            if mod_clean is None:
                raise ValueError(f"unsupported modifier {mod!r}")
            modifiers.append(f"{mod_clean} down")
        using = f"using {{{', '.join(modifiers)}}}" if modifiers else ""
        script = f'Application("System Events").keystroke("{key}") {using};'
        await self._applescript.run(script)

    async def install_apk(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("APK install is Android-only")

    async def ax_tree(self, bundle_id: str | None = None) -> Any:
        if bundle_id is None:
            return None
        elem = self._ax.get_app_element(bundle_id)
        if elem is None:
            return None
        return self._ax.summarise(elem).__dict__

    async def storage_state_save(self, provider: str, project_slug: str | None = None):  # type: ignore[no-untyped-def]
        raise NotImplementedError("desktop driver storage_state not supported")

    async def storage_state_load(self, provider: str, project_slug: str | None = None):  # type: ignore[no-untyped-def]
        raise NotImplementedError("desktop driver storage_state not supported")
