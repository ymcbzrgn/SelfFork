"""VR/AR tool helpers — Quest + VisionPro gate + invoke shims.

S-ToolFleet Faz 4. Mirrors :mod:`tools.mobile._internal` /
:mod:`tools.browser._internal` / :mod:`tools.desktop._internal`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from selffork_orchestrator.tools.base import ToolContext, raise_unauthorized
from selffork_orchestrator.tools.body._internal import _invoke as _body_invoke

__all__ = [
    "_invoke_vr",
    "_require_quest_driver",
    "_require_visionpro_driver",
]


def _require_quest_driver(ctx: ToolContext) -> Any:
    """Return the Quest 3 driver. Unauthorized when missing / wrong platform."""
    drv = ctx.body_driver
    if drv is None:
        raise_unauthorized(
            "this tool requires a Quest 3 driver; set "
            "SELFFORK_BODY_PLATFORM=quest and ensure the headset is "
            "reachable via `adb devices`",
        )
        raise AssertionError("unreachable")  # pragma: no cover
    platform = getattr(drv, "platform", None)
    if platform == "quest":
        return drv
    raise_unauthorized(
        f"active body driver is platform={platform!r}; this tool requires Quest",
    )
    raise AssertionError("unreachable")  # pragma: no cover


def _require_visionpro_driver(ctx: ToolContext) -> Any:
    """Return the Vision Pro driver. Unauthorized when missing / wrong platform."""
    drv = ctx.body_driver
    if drv is None:
        raise_unauthorized(
            "this tool requires a Vision Pro driver; set "
            "SELFFORK_BODY_PLATFORM=visionpro and ensure the visionOS "
            "simulator is available via `xcrun simctl list`",
        )
        raise AssertionError("unreachable")  # pragma: no cover
    platform = getattr(drv, "platform", None)
    if platform == "visionpro":
        return drv
    raise_unauthorized(
        f"active body driver is platform={platform!r}; this tool requires VisionPro",
    )
    raise AssertionError("unreachable")  # pragma: no cover


async def _invoke_vr(
    ctx: ToolContext,
    *,
    action_type: str,
    target_uri: str | None,
    args_summary: dict[str, Any],
    coro_factory: Callable[[], Awaitable[Any]],
) -> dict[str, Any]:
    """Thin shim over ``tools.body._internal._invoke`` for VR tools."""
    return await _body_invoke(
        ctx,
        action_type=action_type,
        target_uri=target_uri,
        args_summary=args_summary,
        coro_factory=coro_factory,
    )
