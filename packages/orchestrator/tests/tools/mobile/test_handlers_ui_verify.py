"""UI-verify handler dispatch — assertion tools that exercise driver.ax_tree / screenshot."""

from __future__ import annotations

from selffork_orchestrator.tools.mobile.ui_verify import (
    UiVerifyA11yTreeArgs,
    UiVerifyColorAtArgs,
    UiVerifyElementExistsArgs,
    UiVerifyElementStateArgs,
    UiVerifyFocusArgs,
    UiVerifyNoOverflowArgs,
    UiVerifyOcrContainsArgs,
    UiVerifyResponsiveArgs,
    UiVerifyScreenshotMatchArgs,
    UiVerifyTextVisibleArgs,
    _ui_verify_a11y_tree,
    _ui_verify_color_at,
    _ui_verify_element_exists,
    _ui_verify_element_state,
    _ui_verify_focus,
    _ui_verify_no_overflow,
    _ui_verify_ocr_contains,
    _ui_verify_responsive,
    _ui_verify_screenshot_match,
    _ui_verify_text_visible,
)


async def test_a11y_tree_full(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_a11y_tree(ctx_ios, UiVerifyA11yTreeArgs())
    assert result["result"]["tree_chars"] > 0


async def test_a11y_tree_with_selector_matches(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_a11y_tree(ctx_ios, UiVerifyA11yTreeArgs(selector="Submit"))
    assert result["result"]["matched"] >= 1


async def test_text_visible_hit(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_text_visible(
        ctx_ios, UiVerifyTextVisibleArgs(text="Welcome"),
    )
    assert result["result"]["visible"] is True


async def test_text_visible_miss(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_text_visible(
        ctx_ios, UiVerifyTextVisibleArgs(text="absent-token-xyz"),
    )
    assert result["result"]["visible"] is False


async def test_text_visible_case_sensitive(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_text_visible(
        ctx_ios, UiVerifyTextVisibleArgs(text="welcome", case_sensitive=True),
    )
    assert result["result"]["visible"] is False


async def test_element_exists(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_element_exists(
        ctx_ios, UiVerifyElementExistsArgs(selector="Submit"),
    )
    assert result["result"]["exists"] is True


async def test_element_state_visible(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_element_state(
        ctx_ios, UiVerifyElementStateArgs(selector="Submit", state="visible"),
    )
    assert result["result"]["matches"] is True


async def test_element_state_not_found(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_element_state(
        ctx_ios,
        UiVerifyElementStateArgs(selector="DoesNotExist", state="visible"),
    )
    assert result["result"]["matches"] is False


async def test_screenshot_match_actual_sha(ctx_ios, stub_ios_driver) -> None:
    import hashlib

    expected = hashlib.sha256(b"\x89PNG\r\n\x1a\nstub").hexdigest()
    result = await _ui_verify_screenshot_match(
        ctx_ios, UiVerifyScreenshotMatchArgs(reference_sha256=expected),
    )
    assert result["result"]["match"] is True


async def test_screenshot_match_mismatch(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_screenshot_match(
        ctx_ios, UiVerifyScreenshotMatchArgs(reference_sha256="0" * 64),
    )
    assert result["result"]["match"] is False


async def test_ocr_contains_via_ax(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_ocr_contains(
        ctx_ios, UiVerifyOcrContainsArgs(text="Welcome"),
    )
    assert result["result"]["contains"] is True


async def test_color_at_with_valid_png(ctx_ios, stub_ios_driver) -> None:
    # Replace stub's screenshot with a real 4x4 red PNG so PIL can decode.
    from io import BytesIO

    try:
        from PIL import Image
    except ImportError:
        import pytest

        pytest.skip("Pillow not installed")

    img = Image.new("RGB", (4, 4), color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    async def _screenshot(rect=None):
        return png_bytes

    stub_ios_driver.screenshot = _screenshot  # type: ignore[method-assign]

    result = await _ui_verify_color_at(
        ctx_ios, UiVerifyColorAtArgs(x=0, y=0, expected_rgb=(255, 0, 0)),
    )
    assert result["result"]["matches"] is True


async def test_color_at_out_of_bounds(ctx_ios, stub_ios_driver) -> None:
    from io import BytesIO

    try:
        from PIL import Image
    except ImportError:
        import pytest

        pytest.skip("Pillow not installed")

    img = Image.new("RGB", (4, 4), color=(0, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    stub_ios_driver.screenshot = lambda rect=None: _async_bytes(buf.getvalue())  # type: ignore[method-assign]

    async def _async_bytes(b):
        return b

    # Easier: directly assign coroutine factory
    async def _ss(rect=None):
        return buf.getvalue()

    stub_ios_driver.screenshot = _ss  # type: ignore[method-assign]

    result = await _ui_verify_color_at(
        ctx_ios, UiVerifyColorAtArgs(x=100, y=100),
    )
    assert result["result"]["status"] == "out_of_bounds"


async def test_no_overflow(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_no_overflow(ctx_ios, UiVerifyNoOverflowArgs())
    assert "overflows" in result["result"]


async def test_responsive_ack(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_responsive(
        ctx_ios, UiVerifyResponsiveArgs(breakpoints_px=[320, 768]),
    )
    assert result["result"]["status"] == "acknowledged"


async def test_focus(ctx_ios, stub_ios_driver) -> None:
    result = await _ui_verify_focus(ctx_ios, UiVerifyFocusArgs())
    # Stub a11y tree has focused="true"
    assert result["result"]["focused"] is True
