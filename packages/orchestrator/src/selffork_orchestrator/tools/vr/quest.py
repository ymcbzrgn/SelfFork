"""Quest 3 VR tools — Android base + VR-specific extensions (17 tools)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.vr._internal import _invoke_vr, _require_quest_driver

__all__ = [
    "QuestAppLaunchArgs",
    "QuestAppListArgs",
    "QuestAppTerminateArgs",
    "QuestDeviceInfoArgs",
    "QuestGetBatteryArgs",
    "QuestGetBoundaryArgs",
    "QuestInstallApkArgs",
    "QuestListVrAppsArgs",
    "QuestLogcatArgs",
    "QuestPassthroughDisableArgs",
    "QuestPassthroughEnableArgs",
    "QuestPressControllerButtonArgs",
    "QuestPressMetaButtonArgs",
    "QuestRecenterArgs",
    "QuestRecordVideoArgs",
    "QuestScreenshotArgs",
    "QuestStopRecordVideoArgs",
    "QuestUninstallAppArgs",
    "QuestVoiceCommandArgs",
    "build_quest_tools",
]


# ---- Args ----------------------------------------------------------------


class QuestAppLaunchArgs(ToolArgs):
    package: str = Field(min_length=1, max_length=255)


class QuestAppTerminateArgs(ToolArgs):
    package: str = Field(min_length=1, max_length=255)


class QuestAppListArgs(ToolArgs):
    pass


class QuestListVrAppsArgs(ToolArgs):
    pass


class QuestInstallApkArgs(ToolArgs):
    apk_path: str = Field(min_length=1, max_length=4096)


class QuestUninstallAppArgs(ToolArgs):
    package: str = Field(min_length=1, max_length=255)


class QuestScreenshotArgs(ToolArgs):
    pass


class QuestRecenterArgs(ToolArgs):
    pass


class QuestPassthroughEnableArgs(ToolArgs):
    pass


class QuestPassthroughDisableArgs(ToolArgs):
    pass


class QuestPressMetaButtonArgs(ToolArgs):
    pass


class QuestPressControllerButtonArgs(ToolArgs):
    controller: Literal["left", "right"] = "right"
    button: Literal["a", "b", "x", "y", "grip", "trigger", "thumbstick"] = Field(
        description="Quest controller button name",
    )


class QuestGetBatteryArgs(ToolArgs):
    pass


class QuestDeviceInfoArgs(ToolArgs):
    pass


class QuestGetBoundaryArgs(ToolArgs):
    pass


class QuestLogcatArgs(ToolArgs):
    tag_filter: str | None = Field(default=None, max_length=256)
    max_lines: int = Field(default=200, ge=1, le=10_000)


class QuestRecordVideoArgs(ToolArgs):
    output_path: str = Field(min_length=1, max_length=4096)
    time_limit_sec: int = Field(default=60, ge=1, le=600)


class QuestStopRecordVideoArgs(ToolArgs):
    pass


class QuestVoiceCommandArgs(ToolArgs):
    text: str = Field(min_length=1, max_length=2048)


# ---- Handlers ------------------------------------------------------------


async def _quest_app_launch(ctx: ToolContext, args: QuestAppLaunchArgs) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)
    return await _invoke_vr(
        ctx, action_type="quest.app_launch",
        target_uri=f"quest-app:{args.package}",
        args_summary={"package": args.package},
        coro_factory=lambda: drv.app_launch(args.package),
    )


async def _quest_app_terminate(ctx: ToolContext, args: QuestAppTerminateArgs) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)
    return await _invoke_vr(
        ctx, action_type="quest.app_terminate",
        target_uri=f"quest-app:{args.package}",
        args_summary={"package": args.package},
        coro_factory=lambda: drv.app_terminate(args.package),
    )


async def _quest_app_list(ctx: ToolContext, args: QuestAppListArgs) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)

    async def _list() -> dict[str, Any]:
        apps = await drv.list_apps()
        return {"count": len(apps), "apps": apps[:500]}

    return await _invoke_vr(
        ctx, action_type="quest.app_list", target_uri=None,
        args_summary={}, coro_factory=_list,
    )


async def _quest_list_vr_apps(ctx: ToolContext, args: QuestListVrAppsArgs) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)

    async def _list() -> dict[str, Any]:
        apps = await drv.list_installed_vr_apps()
        return {"count": len(apps), "apps": apps[:500]}

    return await _invoke_vr(
        ctx, action_type="quest.list_vr_apps", target_uri=None,
        args_summary={}, coro_factory=_list,
    )


async def _quest_install_apk(ctx: ToolContext, args: QuestInstallApkArgs) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)
    return await _invoke_vr(
        ctx, action_type="quest.install_apk",
        target_uri=f"file:{args.apk_path}",
        args_summary={"apk_path": args.apk_path},
        coro_factory=lambda: drv.install_app(Path(args.apk_path)),
    )


async def _quest_uninstall_app(ctx: ToolContext, args: QuestUninstallAppArgs) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)
    return await _invoke_vr(
        ctx, action_type="quest.uninstall_app",
        target_uri=f"quest-app:{args.package}",
        args_summary={"package": args.package},
        coro_factory=lambda: drv.uninstall_app(args.package),
    )


async def _quest_screenshot(ctx: ToolContext, args: QuestScreenshotArgs) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)

    async def _shot() -> dict[str, Any]:
        png = await drv.screenshot()
        ref = None
        store: Any = ctx.screenshot_store
        if store is not None:
            try:
                ref_obj = store.write(
                    png, session_id=ctx.session_id, project_slug=ctx.project_slug,
                )
                ref = {
                    "path": str(ref_obj.path),
                    "sha256": ref_obj.sha256,
                    "bytes_size": ref_obj.bytes_size,
                }
            except Exception:
                ref = None
        return {"bytes_size": len(png), "ref": ref}

    return await _invoke_vr(
        ctx, action_type="quest.screenshot",
        target_uri=None, args_summary={}, coro_factory=_shot,
    )


async def _quest_recenter(ctx: ToolContext, args: QuestRecenterArgs) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)

    async def _run() -> dict[str, Any]:
        out = await drv.recenter()
        return {"output": out[:1024]}

    return await _invoke_vr(
        ctx, action_type="quest.recenter",
        target_uri=None, args_summary={}, coro_factory=_run,
    )


async def _quest_passthrough_enable(
    ctx: ToolContext, args: QuestPassthroughEnableArgs,
) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)
    return await _invoke_vr(
        ctx, action_type="quest.passthrough_enable",
        target_uri=None, args_summary={},
        coro_factory=lambda: drv.passthrough_enable(),
    )


async def _quest_passthrough_disable(
    ctx: ToolContext, args: QuestPassthroughDisableArgs,
) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)
    return await _invoke_vr(
        ctx, action_type="quest.passthrough_disable",
        target_uri=None, args_summary={},
        coro_factory=lambda: drv.passthrough_disable(),
    )


async def _quest_press_meta_button(
    ctx: ToolContext, args: QuestPressMetaButtonArgs,
) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)
    return await _invoke_vr(
        ctx, action_type="quest.press_meta_button",
        target_uri=None, args_summary={},
        coro_factory=lambda: drv.press_meta_button(),
    )


async def _quest_press_controller_button(
    ctx: ToolContext, args: QuestPressControllerButtonArgs,
) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)
    return await _invoke_vr(
        ctx, action_type="quest.press_controller_button",
        target_uri=None,
        args_summary={"controller": args.controller, "button": args.button},
        coro_factory=lambda: drv.press_controller_button(args.controller, args.button),
    )


async def _quest_get_battery(ctx: ToolContext, args: QuestGetBatteryArgs) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)

    async def _get() -> dict[str, Any]:
        out: dict[str, Any] = await drv.get_combined_battery()
        return out

    return await _invoke_vr(
        ctx, action_type="quest.get_battery",
        target_uri=None, args_summary={}, coro_factory=_get,
    )


async def _quest_device_info(ctx: ToolContext, args: QuestDeviceInfoArgs) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)

    async def _get() -> dict[str, Any]:
        out: dict[str, Any] = await drv.get_device_info()
        return out

    return await _invoke_vr(
        ctx, action_type="quest.device_info",
        target_uri=None, args_summary={}, coro_factory=_get,
    )


async def _quest_get_boundary(
    ctx: ToolContext, args: QuestGetBoundaryArgs,
) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)

    async def _get() -> dict[str, Any]:
        out: dict[str, Any] = await drv.get_boundary_status()
        return out

    return await _invoke_vr(
        ctx, action_type="quest.get_boundary",
        target_uri=None, args_summary={}, coro_factory=_get,
    )


async def _quest_logcat(ctx: ToolContext, args: QuestLogcatArgs) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)

    async def _grab() -> dict[str, Any]:
        text = await drv.logcat(tag_filter=args.tag_filter, max_lines=args.max_lines)
        return {"text_len": len(text), "preview": text[:8192]}

    return await _invoke_vr(
        ctx, action_type="quest.logcat",
        target_uri=None,
        args_summary={
            "tag_filter": args.tag_filter, "max_lines": args.max_lines,
        },
        coro_factory=_grab,
    )


async def _quest_record_video(
    ctx: ToolContext, args: QuestRecordVideoArgs,
) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)
    return await _invoke_vr(
        ctx, action_type="quest.record_video",
        target_uri=f"quest-file:{args.output_path}",
        args_summary={
            "output_path": args.output_path,
            "time_limit_sec": args.time_limit_sec,
        },
        coro_factory=lambda: drv.record_video(
            args.output_path, time_limit_sec=args.time_limit_sec,
        ),
    )


async def _quest_stop_record_video(
    ctx: ToolContext, args: QuestStopRecordVideoArgs,
) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)
    return await _invoke_vr(
        ctx, action_type="quest.stop_record_video",
        target_uri=None, args_summary={},
        coro_factory=lambda: drv.stop_record_video(),
    )


async def _quest_voice_command(
    ctx: ToolContext, args: QuestVoiceCommandArgs,
) -> dict[str, Any]:
    drv = _require_quest_driver(ctx)
    return await _invoke_vr(
        ctx, action_type="quest.voice_command",
        target_uri=None,
        args_summary={"text_len": len(args.text)},
        coro_factory=lambda: drv.voice_command(args.text),
    )


def build_quest_tools() -> list[ToolSpec[Any]]:
    return [
        # Eager (3) — VR observe→act loop core
        ToolSpec(
            name="quest_screenshot",
            description="Capture Quest 3 headset screenshot (Android ADB exec-out).",
            args_model=QuestScreenshotArgs, handler=_quest_screenshot,
            defer_loading=False,
        ),
        ToolSpec(
            name="quest_app_launch",
            description="Launch a Quest 3 VR app by package name.",
            args_model=QuestAppLaunchArgs, handler=_quest_app_launch,
            defer_loading=False,
        ),
        ToolSpec(
            name="quest_recenter",
            description="Recenter the Quest 3 headset view (Meta intent).",
            args_model=QuestRecenterArgs, handler=_quest_recenter,
            defer_loading=False,
        ),
        # Deferred (14)
        ToolSpec(
            name="quest_app_terminate",
            description="Terminate a Quest 3 app by package name (am force-stop).",
            args_model=QuestAppTerminateArgs, handler=_quest_app_terminate,
            defer_loading=True,
        ),
        ToolSpec(
            name="quest_app_list",
            description="List all installed Quest 3 apps.",
            args_model=QuestAppListArgs, handler=_quest_app_list,
            defer_loading=True,
        ),
        ToolSpec(
            name="quest_list_vr_apps",
            description=(
                "List Quest 3 apps with VR/Meta package heuristic flag."
            ),
            args_model=QuestListVrAppsArgs, handler=_quest_list_vr_apps,
            defer_loading=True,
        ),
        ToolSpec(
            name="quest_install_apk",
            description="Sideload an APK onto Quest 3 (adb install -r).",
            args_model=QuestInstallApkArgs, handler=_quest_install_apk,
            defer_loading=True,
        ),
        ToolSpec(
            name="quest_uninstall_app",
            description="Uninstall a Quest 3 app by package (adb uninstall).",
            args_model=QuestUninstallAppArgs, handler=_quest_uninstall_app,
            defer_loading=True,
        ),
        ToolSpec(
            name="quest_passthrough_enable",
            description="Toggle Quest 3 passthrough ON via Meta intent.",
            args_model=QuestPassthroughEnableArgs,
            handler=_quest_passthrough_enable, defer_loading=True,
        ),
        ToolSpec(
            name="quest_passthrough_disable",
            description="Toggle Quest 3 passthrough OFF via Meta intent.",
            args_model=QuestPassthroughDisableArgs,
            handler=_quest_passthrough_disable, defer_loading=True,
        ),
        ToolSpec(
            name="quest_press_meta_button",
            description="Press the Quest Meta/Oculus home button.",
            args_model=QuestPressMetaButtonArgs,
            handler=_quest_press_meta_button, defer_loading=True,
        ),
        ToolSpec(
            name="quest_press_controller_button",
            description=(
                "Press a Quest controller button (a/b/x/y/grip/trigger/"
                "thumbstick on left/right controller)."
            ),
            args_model=QuestPressControllerButtonArgs,
            handler=_quest_press_controller_button, defer_loading=True,
        ),
        ToolSpec(
            name="quest_get_battery",
            description=(
                "Get combined Quest battery info (headset + controllers via "
                "OVRRuntime dumpsys when available)."
            ),
            args_model=QuestGetBatteryArgs, handler=_quest_get_battery,
            defer_loading=True,
        ),
        ToolSpec(
            name="quest_device_info",
            description=(
                "Read Quest model / OS / runtime version via Android getprop."
            ),
            args_model=QuestDeviceInfoArgs, handler=_quest_device_info,
            defer_loading=True,
        ),
        ToolSpec(
            name="quest_get_boundary",
            description="Read Quest Guardian (boundary) status from OVRGuardian dumpsys.",
            args_model=QuestGetBoundaryArgs, handler=_quest_get_boundary,
            defer_loading=True,
        ),
        ToolSpec(
            name="quest_logcat",
            description=(
                "Read Quest device logcat (Android log; optional tag filter)."
            ),
            args_model=QuestLogcatArgs, handler=_quest_logcat,
            defer_loading=True,
        ),
        ToolSpec(
            name="quest_record_video",
            description="Start on-device Quest screenrecord with a time limit.",
            args_model=QuestRecordVideoArgs, handler=_quest_record_video,
            defer_loading=True,
        ),
        ToolSpec(
            name="quest_stop_record_video",
            description="Stop the active Quest screenrecord (SIGINT).",
            args_model=QuestStopRecordVideoArgs,
            handler=_quest_stop_record_video, defer_loading=True,
        ),
        ToolSpec(
            name="quest_voice_command",
            description=(
                "Inject a voice command via Android VOICE_COMMAND intent "
                "(best-effort; voice must be enabled in headset settings)."
            ),
            args_model=QuestVoiceCommandArgs, handler=_quest_voice_command,
            defer_loading=True,
        ),
    ]
