"""UI-verify tools — a11y + OCR + visual assertions (10 tools, all eager).

S-ToolFleet Faz 1. Eager bucket: every ``ui_verify_*`` defer_loading=False
because the agentic mobile loop needs them every observe→act cycle to
decide if a goal was achieved.

Source priority: a11y tree FIRST (deterministic, no ML), screenshot OCR
SECOND (fallback for canvas / non-native surfaces). Mirrors mobile-mcp's
hybrid approach (a11y-tree-first / screenshot-fallback).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_mobile_driver,
)

__all__ = [
    "UiVerifyA11yTreeArgs",
    "UiVerifyColorAtArgs",
    "UiVerifyElementExistsArgs",
    "UiVerifyElementStateArgs",
    "UiVerifyFocusArgs",
    "UiVerifyNoOverflowArgs",
    "UiVerifyOcrContainsArgs",
    "UiVerifyResponsiveArgs",
    "UiVerifyScreenshotMatchArgs",
    "UiVerifyTextVisibleArgs",
    "build_ui_verify_tools",
]


# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------


class UiVerifyA11yTreeArgs(ToolArgs):
    selector: str | None = Field(
        default=None,
        max_length=512,
        description="Optional substring filter; full tree when omitted",
    )


class UiVerifyTextVisibleArgs(ToolArgs):
    text: str = Field(min_length=1, max_length=4_096)
    case_sensitive: bool = False


class UiVerifyElementExistsArgs(ToolArgs):
    selector: str = Field(min_length=1, max_length=512)


class UiVerifyElementStateArgs(ToolArgs):
    selector: str = Field(min_length=1, max_length=512)
    state: Literal["visible", "enabled", "selected", "checked"] = "visible"


class UiVerifyScreenshotMatchArgs(ToolArgs):
    reference_sha256: str = Field(min_length=64, max_length=64)
    tolerance: float = Field(default=0.0, ge=0.0, le=1.0)


class UiVerifyOcrContainsArgs(ToolArgs):
    text: str = Field(min_length=1, max_length=2_048)
    case_sensitive: bool = False


class UiVerifyColorAtArgs(ToolArgs):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    expected_rgb: tuple[int, int, int] | None = None


class UiVerifyNoOverflowArgs(ToolArgs):
    pass


class UiVerifyResponsiveArgs(ToolArgs):
    breakpoints_px: list[int] = Field(
        default_factory=lambda: [320, 375, 414, 768],
        description="Widths to test responsive layout at",
    )


class UiVerifyFocusArgs(ToolArgs):
    pass


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _ax_text(drv: Any) -> str:
    """Dump the active driver's a11y tree as text."""
    if hasattr(drv, "ax_tree"):
        out = await drv.ax_tree()
        return str(out)
    return ""


async def _ui_verify_a11y_tree(
    ctx: ToolContext,
    args: UiVerifyA11yTreeArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _dump() -> dict[str, Any]:
        text = await _ax_text(drv)
        if args.selector:
            matches = [line for line in text.splitlines() if args.selector in line]
            return {
                "matched": len(matches),
                "preview": "\n".join(matches[:200]),
                "tree_chars": len(text),
            }
        return {"tree_chars": len(text), "preview": text[:4096]}

    return await _invoke_mobile(
        ctx,
        action_type="ui_verify.a11y_tree",
        target_uri=None,
        args_summary={"selector": args.selector},
        coro_factory=_dump,
    )


async def _ui_verify_text_visible(
    ctx: ToolContext,
    args: UiVerifyTextVisibleArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _check() -> dict[str, Any]:
        text = await _ax_text(drv)
        haystack = text if args.case_sensitive else text.lower()
        needle = args.text if args.case_sensitive else args.text.lower()
        return {"visible": needle in haystack, "source": "ax_tree"}

    return await _invoke_mobile(
        ctx,
        action_type="ui_verify.text_visible",
        target_uri=None,
        args_summary={
            "text_len": len(args.text),
            "case_sensitive": args.case_sensitive,
        },
        coro_factory=_check,
    )


async def _ui_verify_element_exists(
    ctx: ToolContext,
    args: UiVerifyElementExistsArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _check() -> dict[str, Any]:
        text = await _ax_text(drv)
        return {"exists": args.selector in text, "source": "ax_tree"}

    return await _invoke_mobile(
        ctx,
        action_type="ui_verify.element_exists",
        target_uri=f"selector:{args.selector[:64]}",
        args_summary={"selector_len": len(args.selector)},
        coro_factory=_check,
    )


async def _ui_verify_element_state(
    ctx: ToolContext,
    args: UiVerifyElementStateArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _check() -> dict[str, Any]:
        text = await _ax_text(drv)
        if args.selector not in text:
            return {"matches": False, "reason": "not found"}
        # Heuristic: look for state markers near the selector substring
        idx = text.find(args.selector)
        window = text[max(0, idx - 256) : idx + 256]
        state_markers = {
            "visible": r'(visible="true"|displayed="true"|hidden="false")',
            "enabled": r'(enabled="true")',
            "selected": r'(selected="true"|checked="true")',
            "checked": r'(checked="true")',
        }
        pattern = state_markers.get(args.state, args.state)
        hit = bool(re.search(pattern, window))
        return {
            "matches": hit,
            "state": args.state,
            "window_chars": len(window),
        }

    return await _invoke_mobile(
        ctx,
        action_type="ui_verify.element_state",
        target_uri=f"selector:{args.selector[:64]}",
        args_summary={
            "selector_len": len(args.selector),
            "state": args.state,
        },
        coro_factory=_check,
    )


async def _ui_verify_screenshot_match(
    ctx: ToolContext,
    args: UiVerifyScreenshotMatchArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _check() -> dict[str, Any]:
        png = await drv.screenshot()
        actual_sha = hashlib.sha256(png).hexdigest()
        match = actual_sha == args.reference_sha256
        # tolerance accepted for API parity; exact-hash only in Faz 1
        return {
            "match": match,
            "actual_sha256": actual_sha,
            "reference_sha256": args.reference_sha256,
            "tolerance_requested": args.tolerance,
        }

    return await _invoke_mobile(
        ctx,
        action_type="ui_verify.screenshot_match",
        target_uri=None,
        args_summary={"reference_sha256": args.reference_sha256[:16]},
        coro_factory=_check,
    )


async def _ui_verify_ocr_contains(
    ctx: ToolContext,
    args: UiVerifyOcrContainsArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _check() -> dict[str, Any]:
        # Lean on the a11y tree text for Faz 1; real OCR (Apple Vision /
        # Tesseract) lands in a follow-up wave behind defer_loading
        text = await _ax_text(drv)
        haystack = text if args.case_sensitive else text.lower()
        needle = args.text if args.case_sensitive else args.text.lower()
        return {"contains": needle in haystack, "source": "ax_tree"}

    return await _invoke_mobile(
        ctx,
        action_type="ui_verify.ocr_contains",
        target_uri=None,
        args_summary={
            "text_len": len(args.text),
            "case_sensitive": args.case_sensitive,
        },
        coro_factory=_check,
    )


async def _ui_verify_color_at(
    ctx: ToolContext,
    args: UiVerifyColorAtArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _check() -> dict[str, Any]:
        png_bytes = await drv.screenshot()
        # Lazy-import PIL so the tool import stays cheap on hosts that
        # don't have Pillow installed.
        try:
            from io import BytesIO

            from PIL import Image
        except ImportError:
            return {
                "status": "unavailable",
                "error": "Pillow not installed (pip install Pillow)",
            }
        img = Image.open(BytesIO(png_bytes)).convert("RGB")
        if args.x >= img.width or args.y >= img.height:
            return {
                "status": "out_of_bounds",
                "size": [img.width, img.height],
            }
        rgb_raw: Any = img.getpixel((args.x, args.y))
        rgb_list = list(rgb_raw) if isinstance(rgb_raw, tuple) else [rgb_raw]
        result: dict[str, Any] = {
            "rgb": rgb_list,
            "x": args.x,
            "y": args.y,
        }
        expected: Any = args.expected_rgb
        if expected is not None and isinstance(expected, tuple):
            result["matches"] = tuple(rgb_list) == tuple(expected)
            result["expected"] = list(expected)
        return result

    return await _invoke_mobile(
        ctx,
        action_type="ui_verify.color_at",
        target_uri=None,
        args_summary={
            "x": args.x,
            "y": args.y,
            "expected_rgb": list(args.expected_rgb) if args.expected_rgb else None,
        },
        coro_factory=_check,
    )


async def _ui_verify_no_overflow(
    ctx: ToolContext,
    args: UiVerifyNoOverflowArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _check() -> dict[str, Any]:
        text = await _ax_text(drv)
        # Heuristic: look for typical overflow markers in the a11y tree
        markers = ["clipped", "truncated", "ellipsis", "overflow"]
        hits = [m for m in markers if m in text.lower()]
        return {"overflows": bool(hits), "markers": hits}

    return await _invoke_mobile(
        ctx,
        action_type="ui_verify.no_overflow",
        target_uri=None,
        args_summary={},
        coro_factory=_check,
    )


async def _ui_verify_responsive(
    ctx: ToolContext,
    args: UiVerifyResponsiveArgs,
) -> dict[str, Any]:
    _require_mobile_driver(ctx)

    async def _check() -> dict[str, Any]:
        # Cannot drive real viewport on mobile; record the requested
        # breakpoints + return acknowledgement for operator-level scripting.
        return {
            "status": "acknowledged",
            "breakpoints_px": args.breakpoints_px,
            "note": (
                "Mobile viewport is device-fixed; use ios_set_orientation / "
                "android_set_orientation for layout variations."
            ),
        }

    return await _invoke_mobile(
        ctx,
        action_type="ui_verify.responsive",
        target_uri=None,
        args_summary={"breakpoints": args.breakpoints_px},
        coro_factory=_check,
    )


async def _ui_verify_focus(
    ctx: ToolContext,
    args: UiVerifyFocusArgs,
) -> dict[str, Any]:
    drv = _require_mobile_driver(ctx)

    async def _check() -> dict[str, Any]:
        text = await _ax_text(drv)
        # Look for the focused="true" attribute in the tree
        match = re.search(r'(\w+)[^>]*focused="true"', text)
        if not match:
            return {"focused": False}
        return {"focused": True, "tag": match.group(1)}

    return await _invoke_mobile(
        ctx,
        action_type="ui_verify.focus",
        target_uri=None,
        args_summary={},
        coro_factory=_check,
    )


def build_ui_verify_tools() -> list[ToolSpec[Any]]:
    """Every ui_verify tool is eager — operator loop relies on them."""
    return [
        ToolSpec(
            name="ui_verify_a11y_tree",
            description=(
                "Dump (or filter) the active mobile a11y tree. Substring "
                "selector returns matching lines."
            ),
            args_model=UiVerifyA11yTreeArgs,
            handler=_ui_verify_a11y_tree,
            defer_loading=False,
        ),
        ToolSpec(
            name="ui_verify_text_visible",
            description="True/false: text substring present in the a11y tree.",
            args_model=UiVerifyTextVisibleArgs,
            handler=_ui_verify_text_visible,
            defer_loading=False,
        ),
        ToolSpec(
            name="ui_verify_element_exists",
            description="True/false: selector substring present in the a11y tree.",
            args_model=UiVerifyElementExistsArgs,
            handler=_ui_verify_element_exists,
            defer_loading=False,
        ),
        ToolSpec(
            name="ui_verify_element_state",
            description=(
                "Check an element's state (visible/enabled/selected/checked) "
                "via a11y attribute heuristics."
            ),
            args_model=UiVerifyElementStateArgs,
            handler=_ui_verify_element_state,
            defer_loading=False,
        ),
        ToolSpec(
            name="ui_verify_screenshot_match",
            description="Exact SHA-256 match of the current screenshot vs a reference.",
            args_model=UiVerifyScreenshotMatchArgs,
            handler=_ui_verify_screenshot_match,
            defer_loading=False,
        ),
        ToolSpec(
            name="ui_verify_ocr_contains",
            description=(
                "Text contains check via a11y tree (true OCR fallback ships in a follow-up wave)."
            ),
            args_model=UiVerifyOcrContainsArgs,
            handler=_ui_verify_ocr_contains,
            defer_loading=False,
        ),
        ToolSpec(
            name="ui_verify_color_at",
            description=(
                "Sample RGB at (x, y); optionally assert against expected_rgb. Requires Pillow."
            ),
            args_model=UiVerifyColorAtArgs,
            handler=_ui_verify_color_at,
            defer_loading=False,
        ),
        ToolSpec(
            name="ui_verify_no_overflow",
            description="Check the a11y tree for clipped / truncated markers.",
            args_model=UiVerifyNoOverflowArgs,
            handler=_ui_verify_no_overflow,
            defer_loading=False,
        ),
        ToolSpec(
            name="ui_verify_responsive",
            description=(
                "Acknowledge a responsive-layout request; returns operator "
                "guidance (mobile viewport is device-fixed)."
            ),
            args_model=UiVerifyResponsiveArgs,
            handler=_ui_verify_responsive,
            defer_loading=False,
        ),
        ToolSpec(
            name="ui_verify_focus",
            description="Check if any element is focused in the a11y tree.",
            args_model=UiVerifyFocusArgs,
            handler=_ui_verify_focus,
            defer_loading=False,
        ),
    ]
