"""Pydantic args validation — parameterised across every Faz 1 tool family."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from selffork_orchestrator.tools.mobile.android import (
    intent as android_intent,
)
from selffork_orchestrator.tools.mobile.android import (
    interaction as android_interaction,
)
from selffork_orchestrator.tools.mobile.android import (
    lifecycle as android_lifecycle,
)
from selffork_orchestrator.tools.mobile.android import (
    shell as android_shell,
)
from selffork_orchestrator.tools.mobile.android import (
    system as android_system,
)
from selffork_orchestrator.tools.mobile.crash_state import (
    CrashStateDiffArgs,
    CrashStateRestoreArgs,
    CrashStateSnapshotArgs,
)
from selffork_orchestrator.tools.mobile.expo import (
    ExpoEasBuildArgs,
    ExpoInstallArgs,
)
from selffork_orchestrator.tools.mobile.ios import (
    interaction as ios_interaction,
)
from selffork_orchestrator.tools.mobile.ios import (
    lifecycle as ios_lifecycle,
)
from selffork_orchestrator.tools.mobile.ios import (
    network as ios_network,
)
from selffork_orchestrator.tools.mobile.ios import (
    simulator as ios_simulator,
)
from selffork_orchestrator.tools.mobile.ios import (
    system as ios_system,
)
from selffork_orchestrator.tools.mobile.ui_verify import (
    UiVerifyColorAtArgs,
    UiVerifyOcrContainsArgs,
    UiVerifyScreenshotMatchArgs,
    UiVerifyTextVisibleArgs,
)

# ---------------------------------------------------------------------------
# iOS args
# ---------------------------------------------------------------------------


def test_ios_click_happy() -> None:
    a = ios_interaction.IosClickArgs(x=100, y=200)
    assert a.x == 100 and a.y == 200


def test_ios_click_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        ios_interaction.IosClickArgs(x=-1, y=0)


def test_ios_long_press_duration_bounds() -> None:
    with pytest.raises(ValidationError):
        ios_interaction.IosLongPressArgs(x=0, y=0, duration_ms=99)
    with pytest.raises(ValidationError):
        ios_interaction.IosLongPressArgs(x=0, y=0, duration_ms=10_001)
    ios_interaction.IosLongPressArgs(x=0, y=0, duration_ms=800)


def test_ios_type_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        ios_interaction.IosTypeArgs(text="")


def test_ios_swipe_validates_durations() -> None:
    with pytest.raises(ValidationError):
        ios_interaction.IosSwipeArgs(
            start_x=0,
            start_y=0,
            end_x=10,
            end_y=10,
            duration_ms=10,
        )
    with pytest.raises(ValidationError):
        ios_interaction.IosSwipeArgs(
            start_x=0,
            start_y=0,
            end_x=10,
            end_y=10,
            duration_ms=10_000,
        )


def test_ios_pinch_scale_bounds() -> None:
    with pytest.raises(ValidationError):
        ios_interaction.IosPinchArgs(scale=0.05)
    with pytest.raises(ValidationError):
        ios_interaction.IosPinchArgs(scale=11.0)


def test_ios_press_key_enum() -> None:
    ios_interaction.IosPressKeyArgs(key="home")
    with pytest.raises(ValidationError):
        ios_interaction.IosPressKeyArgs(key="back")  # iOS has no back key


def test_ios_app_launch_requires_bundle() -> None:
    with pytest.raises(ValidationError):
        ios_lifecycle.IosAppLaunchArgs(bundle_id="")


def test_ios_install_app_requires_path() -> None:
    with pytest.raises(ValidationError):
        ios_lifecycle.IosInstallAppArgs(app_path="")


def test_ios_set_orientation_enum() -> None:
    ios_system.IosSetOrientationArgs(orientation="PORTRAIT")
    ios_system.IosSetOrientationArgs(orientation="LANDSCAPE")
    with pytest.raises(ValidationError):
        ios_system.IosSetOrientationArgs(orientation="UPSIDE_DOWN")


def test_ios_press_button_enum() -> None:
    ios_system.IosPressButtonArgs(button="home")
    with pytest.raises(ValidationError):
        ios_system.IosPressButtonArgs(button="back")


def test_ios_set_clipboard_text_bounded() -> None:
    ios_system.IosSetClipboardArgs(text="x" * 100_000)
    with pytest.raises(ValidationError):
        ios_system.IosSetClipboardArgs(text="x" * 100_001)


def test_ios_simulator_boot_requires_udid_len() -> None:
    with pytest.raises(ValidationError):
        ios_simulator.IosSimulatorBootArgs(udid="short")
    ios_simulator.IosSimulatorBootArgs(udid="A" * 36)


def test_ios_set_geolocation_bounds() -> None:
    ios_network.IosSetGeolocationArgs(latitude=0.0, longitude=0.0)
    with pytest.raises(ValidationError):
        ios_network.IosSetGeolocationArgs(latitude=91.0, longitude=0.0)
    with pytest.raises(ValidationError):
        ios_network.IosSetGeolocationArgs(latitude=0.0, longitude=-181.0)


def test_ios_status_bar_override_optional() -> None:
    ios_simulator.IosStatusBarOverrideArgs()
    ios_simulator.IosStatusBarOverrideArgs(time="9:41", battery_state="charged", wifi_bars=3)


def test_ios_set_appearance_enum() -> None:
    ios_simulator.IosSetAppearanceArgs(appearance="dark")
    with pytest.raises(ValidationError):
        ios_simulator.IosSetAppearanceArgs(appearance="auto")


# ---------------------------------------------------------------------------
# Android args
# ---------------------------------------------------------------------------


def test_android_click_negative() -> None:
    with pytest.raises(ValidationError):
        android_interaction.AndroidClickArgs(x=-1, y=0)


def test_android_press_key_enum() -> None:
    android_interaction.AndroidPressKeyArgs(key="back")
    with pytest.raises(ValidationError):
        android_interaction.AndroidPressKeyArgs(key="siri")


def test_android_type_clear_first_default_false() -> None:
    a = android_interaction.AndroidTypeArgs(text="hello")
    assert a.clear_first is False


def test_android_lifecycle_requires_package() -> None:
    with pytest.raises(ValidationError):
        android_lifecycle.AndroidAppLaunchArgs(package="")
    with pytest.raises(ValidationError):
        android_lifecycle.AndroidAppForceStopArgs(package="")


def test_android_system_property_constraints() -> None:
    android_system.AndroidGetPropertyArgs(key="ro.build.version.sdk")
    with pytest.raises(ValidationError):
        android_system.AndroidGetPropertyArgs(key="x" * 129)


def test_android_intent_extras_optional() -> None:
    android_intent.AndroidIntentArgs(action="android.intent.action.VIEW")
    android_intent.AndroidIntentArgs(
        action="X.ACTION",
        extras={"a": "1"},
        component="pkg/.Cls",
    )


def test_android_press_button_enum() -> None:
    android_intent.AndroidPressButtonArgs(button="back")
    android_intent.AndroidPressButtonArgs(button="volume_up")
    with pytest.raises(ValidationError):
        android_intent.AndroidPressButtonArgs(button="siri")


def test_android_shell_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        android_shell.AndroidShellArgs(command="")


def test_android_logcat_max_lines_bounds() -> None:
    android_shell.AndroidLogcatArgs(max_lines=1)
    android_shell.AndroidLogcatArgs(max_lines=10_000)
    with pytest.raises(ValidationError):
        android_shell.AndroidLogcatArgs(max_lines=0)
    with pytest.raises(ValidationError):
        android_shell.AndroidLogcatArgs(max_lines=10_001)


def test_android_set_orientation_enum() -> None:
    android_system.AndroidSetOrientationArgs(orientation="LANDSCAPE_REVERSE")
    with pytest.raises(ValidationError):
        android_system.AndroidSetOrientationArgs(orientation="random")


# ---------------------------------------------------------------------------
# Expo args
# ---------------------------------------------------------------------------


def test_expo_eas_build_defaults() -> None:
    a = ExpoEasBuildArgs()
    assert a.platform == "all"
    assert a.profile == "preview"
    assert a.local is False


def test_expo_eas_build_platform_enum() -> None:
    ExpoEasBuildArgs(platform="ios")
    ExpoEasBuildArgs(platform="android")
    ExpoEasBuildArgs(platform="all")
    with pytest.raises(ValidationError):
        ExpoEasBuildArgs(platform="windows")


def test_expo_install_requires_package() -> None:
    with pytest.raises(ValidationError):
        ExpoInstallArgs(package="")


# ---------------------------------------------------------------------------
# UI-verify args
# ---------------------------------------------------------------------------


def test_ui_verify_text_visible_default_case_insensitive() -> None:
    a = UiVerifyTextVisibleArgs(text="hello")
    assert a.case_sensitive is False


def test_ui_verify_screenshot_match_sha256_length() -> None:
    UiVerifyScreenshotMatchArgs(reference_sha256="a" * 64)
    with pytest.raises(ValidationError):
        UiVerifyScreenshotMatchArgs(reference_sha256="short")
    with pytest.raises(ValidationError):
        UiVerifyScreenshotMatchArgs(reference_sha256="a" * 65)


def test_ui_verify_screenshot_match_tolerance_bounds() -> None:
    with pytest.raises(ValidationError):
        UiVerifyScreenshotMatchArgs(reference_sha256="a" * 64, tolerance=1.5)


def test_ui_verify_color_at_optional_expected() -> None:
    a = UiVerifyColorAtArgs(x=10, y=20)
    assert a.expected_rgb is None
    UiVerifyColorAtArgs(x=10, y=20, expected_rgb=(255, 0, 0))


def test_ui_verify_ocr_contains_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        UiVerifyOcrContainsArgs(text="")


# ---------------------------------------------------------------------------
# Crash/state args
# ---------------------------------------------------------------------------


def test_crash_state_snapshot_label_required() -> None:
    with pytest.raises(ValidationError):
        CrashStateSnapshotArgs(label="")


def test_crash_state_snapshot_defaults() -> None:
    a = CrashStateSnapshotArgs(label="before")
    assert a.include_a11y is True
    assert a.include_logs is False


def test_crash_state_restore_requires_label() -> None:
    with pytest.raises(ValidationError):
        CrashStateRestoreArgs(label="")


def test_crash_state_diff_two_labels() -> None:
    CrashStateDiffArgs(label_a="before", label_b="after")
    with pytest.raises(ValidationError):
        CrashStateDiffArgs(label_a="", label_b="after")
