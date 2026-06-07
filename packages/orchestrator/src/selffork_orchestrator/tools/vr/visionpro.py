"""Vision Pro VR tools — vision-only via simctl + AppleScript + LLM OCR (8 tools)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.vr._internal import (
    _invoke_vr,
    _require_visionpro_driver,
)

__all__ = [
    "VisionProAppLaunchArgs",
    "VisionProClickAtArgs",
    "VisionProFindTextArgs",
    "VisionProGetLogsArgs",
    "VisionProScreenshotArgs",
    "VisionProSimulatorBootArgs",
    "VisionProSimulatorListArgs",
    "VisionProSimulatorShutdownArgs",
    "build_visionpro_tools",
]


class VisionProSimulatorListArgs(ToolArgs):
    pass


class VisionProSimulatorBootArgs(ToolArgs):
    udid: str = Field(min_length=10)


class VisionProSimulatorShutdownArgs(ToolArgs):
    udid: str = Field(min_length=10)


class VisionProScreenshotArgs(ToolArgs):
    pass


class VisionProAppLaunchArgs(ToolArgs):
    bundle_id: str = Field(min_length=1, max_length=255)


class VisionProGetLogsArgs(ToolArgs):
    predicate: str | None = Field(default=None, max_length=2048)
    last: str = Field(default="1m", max_length=32)


class VisionProFindTextArgs(ToolArgs):
    needle: str = Field(min_length=1, max_length=1024)


class VisionProClickAtArgs(ToolArgs):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


# ---- Handlers ------------------------------------------------------------


async def _visionpro_simulator_list(
    ctx: ToolContext,
    args: VisionProSimulatorListArgs,
) -> dict[str, Any]:
    drv = _require_visionpro_driver(ctx)

    async def _list() -> dict[str, Any]:
        devices = await drv.simulator_list()
        return {"count": len(devices), "devices": devices[:50]}

    return await _invoke_vr(
        ctx,
        action_type="visionpro.simulator_list",
        target_uri=None,
        args_summary={},
        coro_factory=_list,
    )


async def _visionpro_simulator_boot(
    ctx: ToolContext,
    args: VisionProSimulatorBootArgs,
) -> dict[str, Any]:
    drv = _require_visionpro_driver(ctx)

    async def _boot() -> dict[str, Any]:
        udid = await drv.simulator_boot(args.udid)
        return {"udid": udid}

    return await _invoke_vr(
        ctx,
        action_type="visionpro.simulator_boot",
        target_uri=f"vp-sim:{args.udid}",
        args_summary={"udid": args.udid},
        coro_factory=_boot,
    )


async def _visionpro_simulator_shutdown(
    ctx: ToolContext,
    args: VisionProSimulatorShutdownArgs,
) -> dict[str, Any]:
    drv = _require_visionpro_driver(ctx)
    return await _invoke_vr(
        ctx,
        action_type="visionpro.simulator_shutdown",
        target_uri=f"vp-sim:{args.udid}",
        args_summary={"udid": args.udid},
        coro_factory=lambda: drv.simulator_shutdown(args.udid),
    )


async def _visionpro_screenshot(
    ctx: ToolContext,
    args: VisionProScreenshotArgs,
) -> dict[str, Any]:
    drv = _require_visionpro_driver(ctx)

    async def _shot() -> dict[str, Any]:
        png = await drv.screenshot()
        ref = None
        store: Any = ctx.screenshot_store
        if store is not None:
            try:
                ref_obj = store.write(
                    png,
                    session_id=ctx.session_id,
                    project_slug=ctx.project_slug,
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
        ctx,
        action_type="visionpro.screenshot",
        target_uri=None,
        args_summary={},
        coro_factory=_shot,
    )


async def _visionpro_app_launch(
    ctx: ToolContext,
    args: VisionProAppLaunchArgs,
) -> dict[str, Any]:
    drv = _require_visionpro_driver(ctx)
    return await _invoke_vr(
        ctx,
        action_type="visionpro.app_launch",
        target_uri=f"vp-app:{args.bundle_id}",
        args_summary={"bundle_id": args.bundle_id},
        coro_factory=lambda: drv.app_launch(args.bundle_id),
    )


async def _visionpro_get_logs(
    ctx: ToolContext,
    args: VisionProGetLogsArgs,
) -> dict[str, Any]:
    drv = _require_visionpro_driver(ctx)

    async def _grab() -> dict[str, Any]:
        text = await drv.get_logs(predicate=args.predicate, last=args.last)
        return {"text_len": len(text), "preview": text[:8192]}

    return await _invoke_vr(
        ctx,
        action_type="visionpro.get_logs",
        target_uri=None,
        args_summary={"predicate": args.predicate, "last": args.last},
        coro_factory=_grab,
    )


async def _visionpro_find_text(
    ctx: ToolContext,
    args: VisionProFindTextArgs,
) -> dict[str, Any]:
    """LLM-driven OCR: screenshot + ask vision_runtime to locate text bbox.

    Returns ``{"status": "unwired"}`` when ``ctx.vision_runtime`` is
    absent — same pattern as ``browser_act`` / ``browser_extract``.
    """
    drv = _require_visionpro_driver(ctx)
    vision = ctx.vision_runtime

    async def _find() -> dict[str, Any]:
        if vision is None:
            return {
                "status": "unwired",
                "reason": (
                    "no vision_runtime in ToolContext — wire one for "
                    "OCR-driven Vision Pro text finding"
                ),
            }
        png = await drv.screenshot()
        decide = getattr(vision, "decide", None)
        if decide is None:
            return {"status": "unwired", "reason": "vision_runtime missing .decide"}
        prompt = (
            f"Locate the text {args.needle!r} in the screenshot. "
            "Return JSON: {found: bool, x: int, y: int, width: int, height: int}"
        )
        raw = await decide(prompt=prompt, image=png)
        text = str(raw)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {"status": "ok_partial", "raw": text[:4096]}
        return {"status": "ok", "result": data}

    return await _invoke_vr(
        ctx,
        action_type="visionpro.find_text",
        target_uri=None,
        args_summary={"needle_len": len(args.needle)},
        coro_factory=_find,
    )


async def _visionpro_click_at(
    ctx: ToolContext,
    args: VisionProClickAtArgs,
) -> dict[str, Any]:
    drv = _require_visionpro_driver(ctx)
    return await _invoke_vr(
        ctx,
        action_type="visionpro.click_at",
        target_uri=f"coords:{args.x},{args.y}",
        args_summary={"x": args.x, "y": args.y},
        coro_factory=lambda: drv.click_at(args.x, args.y),
    )


def build_visionpro_tools() -> list[ToolSpec[Any]]:
    """All deferred — Vision Pro is niche, vision-only modality."""
    return [
        ToolSpec(
            name="visionpro_simulator_list",
            description="List visionOS simulators (filtered by runtime).",
            args_model=VisionProSimulatorListArgs,
            handler=_visionpro_simulator_list,
            defer_loading=True,
        ),
        ToolSpec(
            name="visionpro_simulator_boot",
            description="Boot a visionOS simulator by UDID.",
            args_model=VisionProSimulatorBootArgs,
            handler=_visionpro_simulator_boot,
            defer_loading=True,
        ),
        ToolSpec(
            name="visionpro_simulator_shutdown",
            description="Shut down a visionOS simulator by UDID.",
            args_model=VisionProSimulatorShutdownArgs,
            handler=_visionpro_simulator_shutdown,
            defer_loading=True,
        ),
        ToolSpec(
            name="visionpro_screenshot",
            description=(
                "Capture visionOS simulator frame (xcrun simctl io screenshot); "
                "persists to ScreenshotStore when wired."
            ),
            args_model=VisionProScreenshotArgs,
            handler=_visionpro_screenshot,
            defer_loading=True,
        ),
        ToolSpec(
            name="visionpro_app_launch",
            description="Launch a visionOS app by bundle ID (simctl launch).",
            args_model=VisionProAppLaunchArgs,
            handler=_visionpro_app_launch,
            defer_loading=True,
        ),
        ToolSpec(
            name="visionpro_get_logs",
            description="Read visionOS unified logs (filterable by predicate + window).",
            args_model=VisionProGetLogsArgs,
            handler=_visionpro_get_logs,
            defer_loading=True,
        ),
        ToolSpec(
            name="visionpro_find_text",
            description=(
                "Locate text on the visionOS screen via LLM-driven OCR "
                "(requires vision_runtime; returns 'unwired' otherwise)."
            ),
            args_model=VisionProFindTextArgs,
            handler=_visionpro_find_text,
            defer_loading=True,
        ),
        ToolSpec(
            name="visionpro_click_at",
            description=(
                "Best-effort host-Mac pointer click at (x, y) on the visionOS "
                "simulator window; operator must keep the sim window focused."
            ),
            args_model=VisionProClickAtArgs,
            handler=_visionpro_click_at,
            defer_loading=True,
        ),
    ]
