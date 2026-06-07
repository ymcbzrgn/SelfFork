"""VR handler dispatch tests."""

from __future__ import annotations

import pytest

from selffork_orchestrator.tools.base import _UnauthorizedError
from selffork_orchestrator.tools.vr._internal import (
    _require_quest_driver,
    _require_visionpro_driver,
)
from selffork_orchestrator.tools.vr.quest import (
    QuestAppLaunchArgs,
    QuestAppListArgs,
    QuestAppTerminateArgs,
    QuestDeviceInfoArgs,
    QuestGetBatteryArgs,
    QuestGetBoundaryArgs,
    QuestInstallApkArgs,
    QuestListVrAppsArgs,
    QuestLogcatArgs,
    QuestPassthroughDisableArgs,
    QuestPassthroughEnableArgs,
    QuestPressControllerButtonArgs,
    QuestPressMetaButtonArgs,
    QuestRecenterArgs,
    QuestRecordVideoArgs,
    QuestScreenshotArgs,
    QuestStopRecordVideoArgs,
    QuestUninstallAppArgs,
    QuestVoiceCommandArgs,
    _quest_app_launch,
    _quest_app_list,
    _quest_app_terminate,
    _quest_device_info,
    _quest_get_battery,
    _quest_get_boundary,
    _quest_install_apk,
    _quest_list_vr_apps,
    _quest_logcat,
    _quest_passthrough_disable,
    _quest_passthrough_enable,
    _quest_press_controller_button,
    _quest_press_meta_button,
    _quest_recenter,
    _quest_record_video,
    _quest_screenshot,
    _quest_stop_record_video,
    _quest_uninstall_app,
    _quest_voice_command,
)
from selffork_orchestrator.tools.vr.visionpro import (
    VisionProAppLaunchArgs,
    VisionProClickAtArgs,
    VisionProFindTextArgs,
    VisionProGetLogsArgs,
    VisionProScreenshotArgs,
    VisionProSimulatorBootArgs,
    VisionProSimulatorListArgs,
    VisionProSimulatorShutdownArgs,
    _visionpro_app_launch,
    _visionpro_click_at,
    _visionpro_find_text,
    _visionpro_get_logs,
    _visionpro_screenshot,
    _visionpro_simulator_boot,
    _visionpro_simulator_list,
    _visionpro_simulator_shutdown,
)

# ---- Gate ----------------------------------------------------------------


async def test_require_quest_driver(ctx_quest, stub_quest_driver) -> None:
    assert _require_quest_driver(ctx_quest) is stub_quest_driver


async def test_require_quest_driver_no_driver(ctx_no_driver) -> None:
    with pytest.raises(_UnauthorizedError):
        _require_quest_driver(ctx_no_driver)


async def test_require_quest_driver_rejects_visionpro(ctx_visionpro) -> None:
    with pytest.raises(_UnauthorizedError):
        _require_quest_driver(ctx_visionpro)


async def test_require_visionpro_driver(ctx_visionpro, stub_visionpro_driver) -> None:
    assert _require_visionpro_driver(ctx_visionpro) is stub_visionpro_driver


async def test_require_visionpro_driver_rejects_quest(ctx_quest) -> None:
    with pytest.raises(_UnauthorizedError):
        _require_visionpro_driver(ctx_quest)


# ---- Quest (19) ----------------------------------------------------------


async def test_quest_screenshot(ctx_quest, stub_quest_driver) -> None:
    result = await _quest_screenshot(ctx_quest, QuestScreenshotArgs())
    assert result["result"]["bytes_size"] > 0


async def test_quest_app_launch(ctx_quest, stub_quest_driver) -> None:
    await _quest_app_launch(
        ctx_quest,
        QuestAppLaunchArgs(package="com.oculus.firstcontact"),
    )
    assert ("app_launch", ("com.oculus.firstcontact",), {}) in stub_quest_driver.calls


async def test_quest_recenter(ctx_quest, stub_quest_driver) -> None:
    result = await _quest_recenter(ctx_quest, QuestRecenterArgs())
    assert result["status"] == "ok"
    assert any(c[0] == "recenter" for c in stub_quest_driver.calls)


async def test_quest_app_terminate(ctx_quest, stub_quest_driver) -> None:
    await _quest_app_terminate(ctx_quest, QuestAppTerminateArgs(package="com.x"))
    assert ("app_terminate", ("com.x",), {}) in stub_quest_driver.calls


async def test_quest_app_list(ctx_quest, stub_quest_driver) -> None:
    result = await _quest_app_list(ctx_quest, QuestAppListArgs())
    assert result["result"]["count"] == 1


async def test_quest_list_vr_apps(ctx_quest, stub_quest_driver) -> None:
    result = await _quest_list_vr_apps(ctx_quest, QuestListVrAppsArgs())
    assert result["result"]["count"] == 1


async def test_quest_install_apk(ctx_quest, stub_quest_driver) -> None:
    await _quest_install_apk(ctx_quest, QuestInstallApkArgs(apk_path="/tmp/x.apk"))
    assert any(c[0] == "install_app" for c in stub_quest_driver.calls)


async def test_quest_uninstall_app(ctx_quest, stub_quest_driver) -> None:
    await _quest_uninstall_app(ctx_quest, QuestUninstallAppArgs(package="com.x"))
    assert ("uninstall_app", ("com.x",), {}) in stub_quest_driver.calls


async def test_quest_passthrough_enable(ctx_quest, stub_quest_driver) -> None:
    await _quest_passthrough_enable(ctx_quest, QuestPassthroughEnableArgs())
    assert ("passthrough_enable", (), {}) in stub_quest_driver.calls


async def test_quest_passthrough_disable(ctx_quest, stub_quest_driver) -> None:
    await _quest_passthrough_disable(ctx_quest, QuestPassthroughDisableArgs())
    assert ("passthrough_disable", (), {}) in stub_quest_driver.calls


async def test_quest_press_meta_button(ctx_quest, stub_quest_driver) -> None:
    await _quest_press_meta_button(ctx_quest, QuestPressMetaButtonArgs())
    assert ("press_meta_button", (), {}) in stub_quest_driver.calls


async def test_quest_press_controller_button(ctx_quest, stub_quest_driver) -> None:
    await _quest_press_controller_button(
        ctx_quest,
        QuestPressControllerButtonArgs(controller="right", button="trigger"),
    )
    assert ("press_controller_button", ("right", "trigger"), {}) in stub_quest_driver.calls


async def test_quest_get_battery(ctx_quest, stub_quest_driver) -> None:
    result = await _quest_get_battery(ctx_quest, QuestGetBatteryArgs())
    assert result["result"]["headset_level"] == "85"


async def test_quest_device_info(ctx_quest, stub_quest_driver) -> None:
    result = await _quest_device_info(ctx_quest, QuestDeviceInfoArgs())
    assert "Quest 3" in str(result["result"])


async def test_quest_get_boundary(ctx_quest, stub_quest_driver) -> None:
    result = await _quest_get_boundary(ctx_quest, QuestGetBoundaryArgs())
    assert "guardian_active" in result["result"]


async def test_quest_logcat(ctx_quest, stub_quest_driver) -> None:
    result = await _quest_logcat(ctx_quest, QuestLogcatArgs(max_lines=50))
    assert result["result"]["text_len"] > 0


async def test_quest_record_video(ctx_quest, stub_quest_driver) -> None:
    await _quest_record_video(
        ctx_quest,
        QuestRecordVideoArgs(output_path="/tmp/v.mp4", time_limit_sec=10),
    )
    assert any(c[0] == "record_video" for c in stub_quest_driver.calls)


async def test_quest_stop_record_video(ctx_quest, stub_quest_driver) -> None:
    await _quest_stop_record_video(ctx_quest, QuestStopRecordVideoArgs())
    assert ("stop_record_video", (), {}) in stub_quest_driver.calls


async def test_quest_voice_command(ctx_quest, stub_quest_driver) -> None:
    await _quest_voice_command(
        ctx_quest,
        QuestVoiceCommandArgs(text="hello quest"),
    )
    assert ("voice_command", ("hello quest",), {}) in stub_quest_driver.calls


# ---- VisionPro (8) -------------------------------------------------------


async def test_visionpro_simulator_list(ctx_visionpro, stub_visionpro_driver) -> None:
    result = await _visionpro_simulator_list(
        ctx_visionpro,
        VisionProSimulatorListArgs(),
    )
    assert result["result"]["count"] == 1


async def test_visionpro_simulator_boot(ctx_visionpro, stub_visionpro_driver) -> None:
    udid = "A" * 36
    result = await _visionpro_simulator_boot(
        ctx_visionpro,
        VisionProSimulatorBootArgs(udid=udid),
    )
    assert result["result"]["udid"] == udid


async def test_visionpro_simulator_shutdown(
    ctx_visionpro,
    stub_visionpro_driver,
) -> None:
    udid = "A" * 36
    await _visionpro_simulator_shutdown(
        ctx_visionpro,
        VisionProSimulatorShutdownArgs(udid=udid),
    )
    assert ("simulator_shutdown", (udid,), {}) in stub_visionpro_driver.calls


async def test_visionpro_screenshot(ctx_visionpro, stub_visionpro_driver) -> None:
    result = await _visionpro_screenshot(ctx_visionpro, VisionProScreenshotArgs())
    assert result["result"]["bytes_size"] > 0


async def test_visionpro_app_launch(ctx_visionpro, stub_visionpro_driver) -> None:
    await _visionpro_app_launch(
        ctx_visionpro,
        VisionProAppLaunchArgs(bundle_id="com.test"),
    )
    assert ("app_launch", ("com.test",), {}) in stub_visionpro_driver.calls


async def test_visionpro_get_logs(ctx_visionpro, stub_visionpro_driver) -> None:
    result = await _visionpro_get_logs(ctx_visionpro, VisionProGetLogsArgs())
    assert result["result"]["text_len"] > 0


async def test_visionpro_find_text_unwired(
    ctx_visionpro,
    stub_visionpro_driver,
) -> None:
    """Without vision_runtime, returns 'unwired' (same as browser_act)."""
    result = await _visionpro_find_text(
        ctx_visionpro,
        VisionProFindTextArgs(needle="Hello"),
    )
    assert result["result"]["status"] == "unwired"


async def test_visionpro_find_text_with_vision(
    stub_visionpro_driver,
) -> None:
    """With vision_runtime wired, dispatches to LLM."""
    from selffork_body.sandbox import PermissionWarden, WardenMode
    from selffork_orchestrator.tools.base import ToolContext

    class _StubProjectStore:
        pass

    class _StubVision:
        async def decide(self, *, prompt, image):
            return '{"found": true, "x": 100, "y": 200, "width": 50, "height": 20}'

    ctx = ToolContext(
        session_id="s",
        project_slug=None,
        project_store=_StubProjectStore(),
        body_driver=stub_visionpro_driver,
        permission_warden=PermissionWarden(mode=WardenMode.DANGER_FULL_ACCESS),
        vision_runtime=_StubVision(),
    )
    result = await _visionpro_find_text(ctx, VisionProFindTextArgs(needle="Hello"))
    assert result["result"]["status"] == "ok"
    assert result["result"]["result"]["found"] is True


async def test_visionpro_click_at(ctx_visionpro, stub_visionpro_driver) -> None:
    await _visionpro_click_at(
        ctx_visionpro,
        VisionProClickAtArgs(x=500, y=300),
    )
    assert ("click_at", (500, 300), {}) in stub_visionpro_driver.calls
