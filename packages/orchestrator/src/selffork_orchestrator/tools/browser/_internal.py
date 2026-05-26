"""Browser tool helpers — driver gating + gate/invoke wrapper.

S-ToolFleet Faz 2. Mirrors :mod:`tools.mobile._internal` (same warden
gate + audit emit + driver dispatch contract) but checks
``platform == "web"`` on the body driver.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from selffork_orchestrator.tools.base import ToolContext, raise_unauthorized
from selffork_orchestrator.tools.body._internal import _invoke as _body_invoke

__all__ = [
    "_invoke_browser",
    "_require_browser_driver",
]


def _require_browser_driver(ctx: ToolContext) -> Any:
    """Return the web body driver. Unauthorized when wrong platform / missing."""
    drv = ctx.body_driver
    if drv is None:
        raise_unauthorized(
            "this tool requires a browser driver; set SELFFORK_BODY_PLATFORM=web "
            "and rerun `selffork run`",
        )
        raise AssertionError("unreachable")  # pragma: no cover
    platform = getattr(drv, "platform", None)
    if platform == "web":
        return drv
    raise_unauthorized(
        f"active body driver is platform={platform!r}; this tool requires web",
    )
    raise AssertionError("unreachable")  # pragma: no cover


async def _invoke_browser(
    ctx: ToolContext,
    *,
    action_type: str,
    target_uri: str | None,
    args_summary: dict[str, Any],
    coro_factory: Callable[[], Awaitable[Any]],
) -> dict[str, Any]:
    """Thin shim over ``tools.body._internal._invoke`` for browser tools."""
    return await _body_invoke(
        ctx,
        action_type=action_type,
        target_uri=target_uri,
        args_summary=args_summary,
        coro_factory=coro_factory,
    )
