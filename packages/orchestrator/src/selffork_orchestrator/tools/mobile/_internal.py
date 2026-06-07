"""Mobile tool helpers — platform routing + gate/invoke wrapper.

S-ToolFleet Faz 1. Mirrors :mod:`tools.body._internal` (sharing the
warden gate + audit emit + driver dispatch) but adds platform routing
so an ``ios_*`` tool reaches the iOS driver even when the body driver
is a :class:`CompositeMobileDriver`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from selffork_orchestrator.tools.base import (
    ToolContext,
    raise_unauthorized,
)
from selffork_orchestrator.tools.body._internal import _invoke as _body_invoke

__all__ = [
    "_invoke_mobile",
    "_require_android_driver",
    "_require_ios_driver",
    "_require_mobile_driver",
]


def _require_mobile_driver(ctx: ToolContext) -> Any:
    """Return the body driver, raise unauthorized if missing."""
    drv = ctx.body_driver
    if drv is None:
        raise_unauthorized(
            "this tool requires a body driver; set SELFFORK_BODY_PLATFORM "
            "(ios|android|both) and rerun `selffork run`",
        )
        raise AssertionError("unreachable")  # pragma: no cover
    return drv


def _require_ios_driver(ctx: ToolContext) -> Any:
    """Return the iOS driver (or composite.ios). Unauthorized on miss.

    Accepts:
    * an :class:`IosDriver` (single-platform run)
    * a :class:`CompositeMobileDriver` with ``.ios is not None``
    """
    drv = _require_mobile_driver(ctx)
    platform = getattr(drv, "platform", None)
    if platform == "ios":
        return drv
    if platform == "composite":
        ios = getattr(drv, "ios", None)
        if ios is not None:
            return ios
        raise_unauthorized(
            "composite body driver has no iOS leg; set SELFFORK_BODY_PLATFORM=both or =ios",
        )
        raise AssertionError("unreachable")  # pragma: no cover
    raise_unauthorized(
        f"active body driver is platform={platform!r}; this tool requires iOS",
    )
    raise AssertionError("unreachable")  # pragma: no cover


def _require_android_driver(ctx: ToolContext) -> Any:
    """Return the Android (or Quest) driver. Unauthorized on miss.

    S-ToolFleet Faz 4 broadens this to accept Quest 3 (``platform="quest"``)
    since Quest's OS is Android-derived and every standard ``android_*``
    operation works through the same ADB surface.
    """
    drv = _require_mobile_driver(ctx)
    platform = getattr(drv, "platform", None)
    if platform in ("android", "quest"):
        return drv
    if platform == "composite":
        android = getattr(drv, "android", None)
        if android is not None:
            return android
        raise_unauthorized(
            "composite body driver has no Android leg; set SELFFORK_BODY_PLATFORM=both or =android",
        )
        raise AssertionError("unreachable")  # pragma: no cover
    raise_unauthorized(
        f"active body driver is platform={platform!r}; this tool requires Android",
    )
    raise AssertionError("unreachable")  # pragma: no cover


async def _invoke_mobile(
    ctx: ToolContext,
    *,
    action_type: str,
    target_uri: str | None,
    args_summary: dict[str, Any],
    coro_factory: Callable[[], Awaitable[Any]],
) -> dict[str, Any]:
    """Thin shim over :func:`tools.body._internal._invoke` for mobile tools.

    Mobile tools share the body warden gate + audit emit shape. Kept as
    a separate symbol so future mobile-only behaviour (per-platform
    target_uri rewrites, mobile-specific rate limiting) can live here
    without polluting the body helpers.
    """
    return await _body_invoke(
        ctx,
        action_type=action_type,
        target_uri=target_uri,
        args_summary=args_summary,
        coro_factory=coro_factory,
    )
