"""iOS driver — composition test (no Appium, no simulator boot)."""

from __future__ import annotations

import pytest

from selffork_body.drivers.ios import IosDriver, IosSimulatorRuntime


def test_real_device_runtime_raises() -> None:
    with pytest.raises(NotImplementedError):
        IosDriver(runtime="physical")


def test_simulator_runtime_state_parser_finds_first_shutdown() -> None:
    sample = """
== Devices ==
-- iOS 17.2 --
    iPhone 17 (12345678-1234-1234-1234-123456789ABC) (Shutdown)
    iPhone 17 Pro (ABCDEF01-2345-6789-ABCD-EF0123456789) (Shutdown)
-- iOS 18.1 --
    iPhone Air (FFFFFFFF-AAAA-BBBB-CCCC-DDDDEEEEFFFF) (Booted)
"""
    found = IosSimulatorRuntime._first_with_state(sample, "Shutdown")
    assert found == "12345678-1234-1234-1234-123456789ABC"
    found_booted = IosSimulatorRuntime._first_with_state(sample, "Booted")
    assert found_booted == "FFFFFFFF-AAAA-BBBB-CCCC-DDDDEEEEFFFF"


def test_simulator_runtime_state_parser_no_match() -> None:
    sample = "no devices here"
    assert IosSimulatorRuntime._first_with_state(sample, "Shutdown") is None


async def test_install_apk_not_supported_on_ios() -> None:
    driver = IosDriver(runtime="sim")
    with pytest.raises(NotImplementedError):
        await driver.install_apk("/tmp/whatever.apk")  # type: ignore[arg-type]


async def test_storage_state_not_supported_on_ios() -> None:
    driver = IosDriver(runtime="sim")
    with pytest.raises(NotImplementedError):
        await driver.storage_state_save("codex")
    with pytest.raises(NotImplementedError):
        await driver.storage_state_load("codex")
