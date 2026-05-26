"""Pydantic args validation for Faz 4 VR tools."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from selffork_orchestrator.tools.vr.quest import (
    QuestAppLaunchArgs,
    QuestLogcatArgs,
    QuestPressControllerButtonArgs,
    QuestRecordVideoArgs,
    QuestVoiceCommandArgs,
)
from selffork_orchestrator.tools.vr.visionpro import (
    VisionProAppLaunchArgs,
    VisionProClickAtArgs,
    VisionProFindTextArgs,
    VisionProSimulatorBootArgs,
)

# ---- Quest ----------------------------------------------------------------


def test_quest_app_launch_required() -> None:
    QuestAppLaunchArgs(package="com.oculus.shellenv")
    with pytest.raises(ValidationError):
        QuestAppLaunchArgs(package="")


def test_quest_press_controller_enum() -> None:
    QuestPressControllerButtonArgs(controller="left", button="a")
    QuestPressControllerButtonArgs(controller="right", button="grip")
    with pytest.raises(ValidationError):
        QuestPressControllerButtonArgs(controller="center", button="a")
    with pytest.raises(ValidationError):
        QuestPressControllerButtonArgs(controller="left", button="select")


def test_quest_logcat_max_lines_bounds() -> None:
    QuestLogcatArgs(max_lines=1)
    QuestLogcatArgs(max_lines=10_000)
    with pytest.raises(ValidationError):
        QuestLogcatArgs(max_lines=0)
    with pytest.raises(ValidationError):
        QuestLogcatArgs(max_lines=10_001)


def test_quest_record_video_bounds() -> None:
    QuestRecordVideoArgs(output_path="/tmp/v.mp4", time_limit_sec=1)
    QuestRecordVideoArgs(output_path="/tmp/v.mp4", time_limit_sec=600)
    with pytest.raises(ValidationError):
        QuestRecordVideoArgs(output_path="/tmp/v.mp4", time_limit_sec=0)
    with pytest.raises(ValidationError):
        QuestRecordVideoArgs(output_path="/tmp/v.mp4", time_limit_sec=601)


def test_quest_voice_command_required() -> None:
    with pytest.raises(ValidationError):
        QuestVoiceCommandArgs(text="")


# ---- VisionPro -----------------------------------------------------------


def test_visionpro_simulator_boot_udid_min_length() -> None:
    VisionProSimulatorBootArgs(udid="A" * 36)
    with pytest.raises(ValidationError):
        VisionProSimulatorBootArgs(udid="short")


def test_visionpro_app_launch_required() -> None:
    VisionProAppLaunchArgs(bundle_id="com.apple.test")
    with pytest.raises(ValidationError):
        VisionProAppLaunchArgs(bundle_id="")


def test_visionpro_find_text_required() -> None:
    VisionProFindTextArgs(needle="Hello")
    with pytest.raises(ValidationError):
        VisionProFindTextArgs(needle="")


def test_visionpro_click_at_non_negative() -> None:
    VisionProClickAtArgs(x=0, y=0)
    with pytest.raises(ValidationError):
        VisionProClickAtArgs(x=-1, y=0)
