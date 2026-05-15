"""TmuxDesktopDriver — snapper state read + send-keys structural test."""

from __future__ import annotations

import json

import pytest

from selffork_body.drivers.desktop.tmux import TmuxDesktopDriver


async def test_list_sessions_empty(tmp_path) -> None:
    driver = TmuxDesktopDriver(snapper_root=tmp_path)
    assert await driver.list_sessions() == []


async def test_list_sessions_reads_snapper_state(tmp_path) -> None:
    (tmp_path / "claude.json").write_text(
        json.dumps({"snapshot_at": "2026-05-10T15:00:00Z", "running": True})
    )
    (tmp_path / "codex.json").write_text(
        json.dumps({"snapshot_at": "2026-05-10T15:00:01Z", "running": False})
    )
    driver = TmuxDesktopDriver(snapper_root=tmp_path)
    sessions = await driver.list_sessions()
    cli_names = {s["cli"] for s in sessions}
    assert cli_names == {"claude", "codex"}


async def test_list_sessions_skips_invalid_json(tmp_path) -> None:
    (tmp_path / "broken.json").write_text("not valid {")
    driver = TmuxDesktopDriver(snapper_root=tmp_path)
    assert await driver.list_sessions() == []


async def test_click_not_supported() -> None:
    driver = TmuxDesktopDriver()
    with pytest.raises(NotImplementedError):
        await driver.click()


async def test_screenshot_not_supported() -> None:
    driver = TmuxDesktopDriver()
    with pytest.raises(NotImplementedError):
        await driver.screenshot()
