"""Desktop tool helpers — macOS driver gate + invoke wrapper.

S-ToolFleet Faz 3. Mirrors :mod:`tools.mobile._internal` /
:mod:`tools.browser._internal`. Checks ``platform == "macos"`` on the
body driver.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from selffork_orchestrator.tools.base import ToolContext, raise_unauthorized
from selffork_orchestrator.tools.body._internal import _invoke as _body_invoke

__all__ = [
    "_invoke_desktop",
    "_require_macos_driver",
]


def _require_macos_driver(ctx: ToolContext) -> Any:
    """Return the macOS body driver. Unauthorized when missing / wrong platform."""
    drv = ctx.body_driver
    if drv is None:
        raise_unauthorized(
            "this tool requires a desktop driver; set SELFFORK_BODY_PLATFORM=macos "
            "and rerun `selffork run`",
        )
        raise AssertionError("unreachable")  # pragma: no cover
    platform = getattr(drv, "platform", None)
    if platform == "macos":
        return drv
    raise_unauthorized(
        f"active body driver is platform={platform!r}; this tool requires macos",
    )
    raise AssertionError("unreachable")  # pragma: no cover


async def _invoke_desktop(
    ctx: ToolContext,
    *,
    action_type: str,
    target_uri: str | None,
    args_summary: dict[str, Any],
    coro_factory: Callable[[], Awaitable[Any]],
) -> dict[str, Any]:
    return await _body_invoke(
        ctx,
        action_type=action_type,
        target_uri=target_uri,
        args_summary=args_summary,
        coro_factory=coro_factory,
    )
