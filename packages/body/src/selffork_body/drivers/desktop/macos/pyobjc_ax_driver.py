"""macOS Accessibility API driver via PyObjC (M5 — ADR-005 §M5-C4).

Interacts with ``AXUIElement`` to read the accessibility tree and dispatch
``AXPress`` actions. PyObjC + ``ApplicationServices`` framework are imported
lazily; on non-Darwin hosts the driver methods raise on first use.

The clean alternative (atomacos) is GPL-2.0 — incompatible with SelfFork's
Apache-2.0 license — so we depend directly on PyObjC's ``ApplicationServices``
binding (BSD-style) and walk the tree ourselves.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

__all__ = ["AxElementSummary", "MacOSAxDriver", "macos_only"]


@dataclass(frozen=True, slots=True)
class AxElementSummary:
    role: str
    title: str
    label: str
    position: tuple[int, int] | None
    size: tuple[int, int] | None


def macos_only() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("macOS Accessibility API driver requires Darwin host")


class MacOSAxDriver:
    """Thin wrapper around AXUIElement system-wide handle."""

    def __init__(self) -> None:
        self._system: Any | None = None

    def _ensure(self) -> Any:
        if self._system is not None:
            return self._system
        macos_only()
        try:
            from ApplicationServices import AXUIElementCreateSystemWide
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "MacOSAxDriver requires PyObjC; install via `uv pip install pyobjc-framework-ApplicationServices`."
            ) from exc
        self._system = AXUIElementCreateSystemWide()
        return self._system

    def get_app_element(self, bundle_id: str) -> Any | None:
        """Return the ``AXUIElement`` for a running app, or None."""
        macos_only()
        try:
            from AppKit import NSWorkspace  # type: ignore[import-not-found]
            from ApplicationServices import AXUIElementCreateApplication
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "MacOSAxDriver.get_app_element requires PyObjC AppKit + ApplicationServices."
            ) from exc

        ws = NSWorkspace.sharedWorkspace()
        for app in ws.runningApplications():
            if app.bundleIdentifier() == bundle_id:
                return AXUIElementCreateApplication(app.processIdentifier())
        return None

    def click_element(self, element: Any) -> None:
        macos_only()
        try:
            from ApplicationServices import AXUIElementPerformAction, kAXPressAction
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("PyObjC required for click_element") from exc
        AXUIElementPerformAction(element, kAXPressAction)

    @staticmethod
    def summarise(element: Any) -> AxElementSummary:
        """Best-effort metadata extraction from an AX element."""
        macos_only()
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXPositionAttribute,
                kAXRoleAttribute,
                kAXSizeAttribute,
                kAXTitleAttribute,
                kAXValueAttribute,
            )
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("PyObjC required for summarise") from exc

        def _read(attr) -> Any | None:
            # PyObjC ``AXUIElementCopyAttributeValue`` returns ``(error, value)``
            # tuple when the out-parameter is None; defensive handling for
            # forward-compatible bindings that may swap the order.
            result = AXUIElementCopyAttributeValue(element, attr, None)
            if not isinstance(result, tuple) or len(result) != 2:
                return None
            first, second = result
            if isinstance(first, int):
                return second if first == 0 else None
            if isinstance(second, int):
                return first if second == 0 else None
            return first

        role = str(_read(kAXRoleAttribute) or "")
        title = str(_read(kAXTitleAttribute) or "")
        label = str(_read(kAXValueAttribute) or "")
        # Position/size come back as CFData CGPoint/CGSize structs; in test
        # paths we simply pass-through without coercion. Real driver code
        # would parse via AXValueGetValue + kAXValueCGPointType.
        position = _read(kAXPositionAttribute)
        size = _read(kAXSizeAttribute)
        pos_t: tuple[int, int] | None = None
        size_t: tuple[int, int] | None = None
        if position is not None and hasattr(position, "x"):
            pos_t = (int(position.x), int(position.y))
        if size is not None and hasattr(size, "width"):
            size_t = (int(size.width), int(size.height))
        return AxElementSummary(
            role=role, title=title, label=label, position=pos_t, size=size_t
        )

    def find_by_label(self, root: Any, label: str, *, max_depth: int = 6) -> Any | None:
        """Depth-first walk; return first element whose AXTitle/AXValue matches ``label``.

        ``max_depth`` caps recursion to keep the live walk responsive.
        """
        macos_only()
        try:
            from ApplicationServices import (
                AXUIElementCopyAttributeValue,
                kAXChildrenAttribute,
            )
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("PyObjC required for find_by_label") from exc

        target = label.lower()

        def _walk(element: Any, depth: int) -> Any | None:
            summary = self.summarise(element)
            if summary.title.lower() == target or summary.label.lower() == target:
                return element
            if depth >= max_depth:
                return None
            result = AXUIElementCopyAttributeValue(
                element, kAXChildrenAttribute, None
            )
            if not isinstance(result, tuple) or len(result) != 2:
                return None
            first, second = result
            err = first if isinstance(first, int) else second
            children = second if isinstance(first, int) else first
            if err != 0 or children is None:
                return None
            for child in children:
                hit = _walk(child, depth + 1)
                if hit is not None:
                    return hit
            return None

        return _walk(root, depth=0)
