"""macOS desktop driver — module-level contract test (no PyObjC required)."""

from __future__ import annotations

import pytest

from selffork_body.drivers.desktop.macos import (
    AppleScriptRunner,
    MacOSDesktopDriver,
)


async def test_click_no_bbox_raises() -> None:
    driver = MacOSDesktopDriver()
    with pytest.raises(NotImplementedError):
        await driver.click("Submit")


async def test_swipe_not_implemented() -> None:
    driver = MacOSDesktopDriver()
    with pytest.raises(NotImplementedError):
        await driver.swipe()


async def test_install_apk_not_implemented() -> None:
    driver = MacOSDesktopDriver()
    with pytest.raises(NotImplementedError):
        await driver.install_apk()


async def test_storage_state_not_implemented() -> None:
    driver = MacOSDesktopDriver()
    with pytest.raises(NotImplementedError):
        await driver.storage_state_save("codex")
    with pytest.raises(NotImplementedError):
        await driver.storage_state_load("codex")


def test_press_key_translates_combo_via_applescript() -> None:
    """Static structural test: press_key build the correct osascript string."""
    runner = AppleScriptRunner()
    # The driver feeds osascript with the rendered keystroke command. We
    # don't run osascript here — we just exercise the helper to confirm it
    # constructs without error.
    import asyncio

    async def _capture():
        captured: list[str] = []

        async def _fake_run(script, language="JavaScript"):
            captured.append(script)
            return ""

        runner.run = _fake_run  # type: ignore[assignment]
        driver = MacOSDesktopDriver(applescript=runner)
        await driver.press_key("cmd+t")
        await driver.press_key("ctrl+shift+a")
        return captured

    captured = asyncio.run(_capture())
    assert "command down" in captured[0]
    assert "control down" in captured[1]
    assert "shift down" in captured[1]


def test_press_key_rejects_unknown_modifier() -> None:
    driver = MacOSDesktopDriver()
    import asyncio

    async def _run() -> None:
        await driver.press_key("super+t")

    with pytest.raises(ValueError):
        asyncio.run(_run())


def test_press_key_rejects_empty() -> None:
    driver = MacOSDesktopDriver()
    import asyncio

    async def _run() -> None:
        await driver.press_key("")

    with pytest.raises(ValueError):
        asyncio.run(_run())
