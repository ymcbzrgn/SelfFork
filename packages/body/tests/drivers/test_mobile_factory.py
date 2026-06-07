"""mobile_factory — platform resolution + driver construction + composite routing.

S-ToolFleet Faz 1 §A — F1 WIRE close. Verifies the factory + composite
contract without spinning up real simulators / emulators (drivers are
constructed but never ``.start()``-ed).
"""

from __future__ import annotations

import sys

import pytest

from selffork_body.drivers.android import AndroidDriver
from selffork_body.drivers.ios import IosDriver
from selffork_body.drivers.mobile_factory import (
    BodyDriverProtocol,
    CompositeMobileDriver,
    build_default_body_driver,
    resolve_platform,
)

# ---------------------------------------------------------------------------
# resolve_platform
# ---------------------------------------------------------------------------


def test_resolve_platform_default_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELFFORK_BODY_PLATFORM", raising=False)
    assert resolve_platform() == "none"


def test_resolve_platform_explicit_arg_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFFORK_BODY_PLATFORM", "android")
    assert resolve_platform("ios") == "ios"


def test_resolve_platform_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFFORK_BODY_PLATFORM", "android")
    assert resolve_platform() == "android"


def test_resolve_platform_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFFORK_BODY_PLATFORM", "both")
    assert resolve_platform() == "both"


def test_resolve_platform_unknown_collapses_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFFORK_BODY_PLATFORM", "windows")
    assert resolve_platform() == "none"


def test_resolve_platform_auto_maps_to_host_os(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFFORK_BODY_PLATFORM", "auto")
    resolved = resolve_platform()
    if sys.platform == "darwin":
        assert resolved == "ios"
    elif sys.platform.startswith("linux"):
        assert resolved == "android"
    else:
        assert resolved == "none"


def test_resolve_platform_normalises_casing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFFORK_BODY_PLATFORM", "  IOS ")
    assert resolve_platform() == "ios"


# ---------------------------------------------------------------------------
# build_default_body_driver
# ---------------------------------------------------------------------------


def test_build_default_returns_none_when_platform_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELFFORK_BODY_PLATFORM", raising=False)
    assert build_default_body_driver() is None


def test_build_default_explicit_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFFORK_BODY_PLATFORM", "ios")
    assert build_default_body_driver(platform="none") is None


def test_build_default_ios_returns_ios_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELFFORK_BODY_PLATFORM", raising=False)
    driver = build_default_body_driver(platform="ios")
    assert isinstance(driver, IosDriver)
    assert driver.platform == "ios"
    # Not started — Faz 1 §A factory contract: caller (cli.py) starts.
    assert driver.simulator.booted_id is None


def test_build_default_ios_honours_device_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELFFORK_BODY_PLATFORM", raising=False)
    driver = build_default_body_driver(platform="ios", ios_device="ABCD-1234")
    assert isinstance(driver, IosDriver)
    assert driver.simulator.device_id == "ABCD-1234"


def test_build_default_ios_honours_env_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFFORK_BODY_PLATFORM", "ios")
    monkeypatch.setenv("SELFFORK_BODY_IOS_DEVICE", "ENV-DEVICE-1")
    driver = build_default_body_driver()
    assert isinstance(driver, IosDriver)
    assert driver.simulator.device_id == "ENV-DEVICE-1"


def test_build_default_android_returns_android_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SELFFORK_BODY_PLATFORM", raising=False)
    driver = build_default_body_driver(platform="android")
    assert isinstance(driver, AndroidDriver)
    assert driver.platform == "android"


def test_build_default_android_honours_device_serial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SELFFORK_BODY_PLATFORM", raising=False)
    driver = build_default_body_driver(
        platform="android",
        android_device_serial="emulator-5554",
    )
    assert isinstance(driver, AndroidDriver)
    assert driver.device_serial == "emulator-5554"


def test_build_default_android_runtime_physical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SELFFORK_BODY_PLATFORM", raising=False)
    driver = build_default_body_driver(platform="android", android_runtime="physical")
    assert isinstance(driver, AndroidDriver)
    assert driver.runtime_kind == "physical"
    assert driver.runtime is None  # physical mode skips docker runtime


def test_build_default_both_returns_composite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELFFORK_BODY_PLATFORM", raising=False)
    driver = build_default_body_driver(platform="both")
    assert isinstance(driver, CompositeMobileDriver)
    assert driver.platform == "composite"
    assert isinstance(driver.ios, IosDriver)
    assert isinstance(driver.android, AndroidDriver)


def test_build_default_both_prefer_ios_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELFFORK_BODY_PREFER", raising=False)
    driver = build_default_body_driver(platform="both")
    assert isinstance(driver, CompositeMobileDriver)
    assert driver._primary is driver.ios


def test_build_default_both_prefer_android_via_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SELFFORK_BODY_PREFER", "android")
    driver = build_default_body_driver(platform="both")
    assert isinstance(driver, CompositeMobileDriver)
    assert driver._primary is driver.android


# ---------------------------------------------------------------------------
# CompositeMobileDriver
# ---------------------------------------------------------------------------


class _StubDriver:
    """Stub that records every call — used for routing tests."""

    platform = "stub"

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple[str, tuple, dict]] = []
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def click(self, target, bbox=None, button="left"):
        self.calls.append(("click", (target,), {"bbox": bbox, "button": button}))

    async def type_text(self, text, target=None):
        self.calls.append(("type_text", (text,), {"target": target}))

    async def screenshot(self, rect=None):
        self.calls.append(("screenshot", (), {"rect": rect}))
        return b"\x89PNG\r\n\x1a\nFAKE"

    async def scroll(self, direction="down", amount=300):
        self.calls.append(("scroll", (), {"direction": direction, "amount": amount}))

    async def swipe(self, sx, sy, ex, ey, duration_ms=250):
        self.calls.append(("swipe", (sx, sy, ex, ey), {"duration_ms": duration_ms}))

    async def app_launch(self, bundle_id):
        self.calls.append(("app_launch", (bundle_id,), {}))

    async def press_key(self, key_combo):
        self.calls.append(("press_key", (key_combo,), {}))

    async def ax_tree(self, bundle_id=None):
        self.calls.append(("ax_tree", (), {"bundle_id": bundle_id}))
        return [{"role": "AXButton"}]

    async def storage_state_save(self, provider, project_slug=None):
        self.calls.append(("storage_state_save", (provider,), {"project_slug": project_slug}))
        return "/tmp/auth.json"

    async def storage_state_load(self, provider, project_slug=None):
        self.calls.append(("storage_state_load", (provider,), {"project_slug": project_slug}))
        return True


def test_composite_requires_at_least_one_driver() -> None:
    with pytest.raises(ValueError, match="at least one"):
        CompositeMobileDriver()


def test_composite_routes_to_preferred_default_ios() -> None:
    ios = _StubDriver("ios")
    android = _StubDriver("android")
    composite = CompositeMobileDriver(ios=ios, android=android)  # type: ignore[arg-type]
    assert composite._primary is ios


def test_composite_routes_to_preferred_android() -> None:
    ios = _StubDriver("ios")
    android = _StubDriver("android")
    composite = CompositeMobileDriver(  # type: ignore[arg-type]
        ios=ios,
        android=android,
        prefer="android",
    )
    assert composite._primary is android


def test_composite_routes_to_only_available_when_prefer_missing() -> None:
    android = _StubDriver("android")
    composite = CompositeMobileDriver(android=android, prefer="ios")  # type: ignore[arg-type]
    assert composite._primary is android


async def test_composite_start_starts_both() -> None:
    ios = _StubDriver("ios")
    android = _StubDriver("android")
    composite = CompositeMobileDriver(ios=ios, android=android)  # type: ignore[arg-type]
    await composite.start()
    assert ios.started and android.started


async def test_composite_stop_stops_both_even_if_one_raises() -> None:
    class _Raises(_StubDriver):
        async def stop(self):
            raise RuntimeError("boom")

    ios = _Raises("ios")
    android = _StubDriver("android")
    composite = CompositeMobileDriver(ios=ios, android=android)  # type: ignore[arg-type]
    # Should not raise — best-effort teardown
    await composite.stop()
    assert android.stopped


async def test_composite_click_routes_to_primary() -> None:
    ios = _StubDriver("ios")
    android = _StubDriver("android")
    composite = CompositeMobileDriver(ios=ios, android=android)  # type: ignore[arg-type]
    await composite.click("Submit", bbox=(0, 0, 10, 10), button="left")
    assert ios.calls == [("click", ("Submit",), {"bbox": (0, 0, 10, 10), "button": "left"})]
    assert android.calls == []


async def test_composite_type_routes_to_primary() -> None:
    ios = _StubDriver("ios")
    composite = CompositeMobileDriver(ios=ios)  # type: ignore[arg-type]
    await composite.type_text("hello", target=None)
    assert ios.calls == [("type_text", ("hello",), {"target": None})]


async def test_composite_screenshot_returns_bytes() -> None:
    ios = _StubDriver("ios")
    composite = CompositeMobileDriver(ios=ios)  # type: ignore[arg-type]
    out = await composite.screenshot()
    assert isinstance(out, bytes) and out.startswith(b"\x89PNG")


async def test_composite_scroll_swipe_appkey_ax_storage_route() -> None:
    ios = _StubDriver("ios")
    composite = CompositeMobileDriver(ios=ios)  # type: ignore[arg-type]
    await composite.scroll(direction="up", amount=200)
    await composite.swipe(10, 20, 30, 40, duration_ms=300)
    await composite.app_launch("com.example.app")
    await composite.press_key("home")
    await composite.ax_tree()
    await composite.storage_state_save("anthropic", project_slug="demo")
    await composite.storage_state_load("anthropic", project_slug="demo")
    names = [c[0] for c in ios.calls]
    assert names == [
        "scroll",
        "swipe",
        "app_launch",
        "press_key",
        "ax_tree",
        "storage_state_save",
        "storage_state_load",
    ]


# ---------------------------------------------------------------------------
# Protocol shape (light contract test)
# ---------------------------------------------------------------------------


def test_ios_driver_satisfies_protocol_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELFFORK_BODY_PLATFORM", raising=False)
    driver = build_default_body_driver(platform="ios")
    assert isinstance(driver, BodyDriverProtocol)


def test_android_driver_satisfies_protocol_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELFFORK_BODY_PLATFORM", raising=False)
    driver = build_default_body_driver(platform="android")
    assert isinstance(driver, BodyDriverProtocol)


def test_composite_satisfies_protocol_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELFFORK_BODY_PLATFORM", raising=False)
    driver = build_default_body_driver(platform="both")
    assert isinstance(driver, BodyDriverProtocol)
