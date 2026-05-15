"""Android driver — composition test (no docker, no real device)."""

from __future__ import annotations

import pytest

from selffork_body.drivers.android import (
    AndroidDriver,
    DockerAndroidRuntime,
    MobileMcpAdapter,
    UiAutomator2Fallback,
)


class _StubMcp(MobileMcpAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.tap_calls: list[tuple[int, int]] = []
        self.swipe_calls: list[tuple] = []
        self.type_calls: list[str] = []
        self.app_launch_calls: list[str] = []
        self.press_key_calls: list[str] = []
        self.screenshot_count = 0

    async def tap(self, x: int, y: int) -> None:
        self.tap_calls.append((x, y))

    async def swipe(self, start_x, start_y, end_x, end_y, duration_ms=250) -> None:
        self.swipe_calls.append((start_x, start_y, end_x, end_y, duration_ms))

    async def type_text(self, text: str) -> None:
        self.type_calls.append(text)

    async def screenshot(self) -> bytes:
        self.screenshot_count += 1
        return b"\x89PNG\r\n\x1a\n" + b"x" * 32

    async def app_launch(self, package: str) -> None:
        self.app_launch_calls.append(package)

    async def press_key(self, key) -> None:
        self.press_key_calls.append(key)

    async def dump_a11y_tree(self) -> dict:
        return {"root": []}

    async def close(self) -> None:
        pass


def _driver(mcp: _StubMcp) -> AndroidDriver:
    return AndroidDriver(
        runtime="physical",
        runtime_obj=None,
        mcp=mcp,
        fallback=UiAutomator2Fallback(),
    )


# ---- docker_runtime config / image tag ----


def test_docker_runtime_image_tag_default() -> None:
    rt = DockerAndroidRuntime(android_version="13.0")
    assert rt._image_tag() == "budtmo/docker-android:emulator_13_0"


def test_docker_runtime_image_tag_custom_version() -> None:
    rt = DockerAndroidRuntime(android_version="14.0")
    assert rt._image_tag() == "budtmo/docker-android:emulator_14_0"


def test_docker_runtime_run_command_includes_ports() -> None:
    rt = DockerAndroidRuntime(adb_host_port=5555, web_port=6080, appium_port=4723)
    cmd = rt._docker_run_command()
    assert "--privileged" in cmd
    assert "5555:5555" in cmd
    assert "6080:6080" in cmd


# ---- AndroidDriver action surface ----


async def test_click_uses_bbox_centre() -> None:
    mcp = _StubMcp()
    driver = _driver(mcp)
    await driver.click("Submit", bbox=(100, 200, 60, 40))
    assert mcp.tap_calls == [(130, 220)]  # centre


async def test_click_without_bbox_raises() -> None:
    driver = _driver(_StubMcp())
    with pytest.raises(ValueError):
        await driver.click("Submit", bbox=None)


async def test_type_text_delegates() -> None:
    mcp = _StubMcp()
    driver = _driver(mcp)
    await driver.type_text("hello")
    assert mcp.type_calls == ["hello"]


async def test_screenshot_returns_bytes() -> None:
    mcp = _StubMcp()
    driver = _driver(mcp)
    out = await driver.screenshot()
    assert out.startswith(b"\x89PNG")
    assert mcp.screenshot_count == 1


async def test_scroll_translates_to_swipe() -> None:
    mcp = _StubMcp()
    driver = _driver(mcp)
    await driver.scroll("down", amount=400)
    assert len(mcp.swipe_calls) == 1
    sx, sy, ex, ey, _duration = mcp.swipe_calls[0]
    assert sx == 540 and ex == 540
    assert sy == 1500 and ey == 1100


async def test_app_launch_delegates() -> None:
    mcp = _StubMcp()
    driver = _driver(mcp)
    await driver.app_launch("com.android.chrome")
    assert mcp.app_launch_calls == ["com.android.chrome"]


async def test_press_key_validates() -> None:
    driver = _driver(_StubMcp())
    with pytest.raises(ValueError):
        await driver.press_key("ctrl+a")


async def test_press_key_allows_known() -> None:
    mcp = _StubMcp()
    driver = _driver(mcp)
    await driver.press_key("home")
    assert mcp.press_key_calls == ["home"]


async def test_storage_state_not_supported() -> None:
    driver = _driver(_StubMcp())
    with pytest.raises(NotImplementedError):
        await driver.storage_state_save("codex")
    with pytest.raises(NotImplementedError):
        await driver.storage_state_load("codex")
