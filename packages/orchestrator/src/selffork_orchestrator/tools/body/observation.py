"""Body observation tools — screenshot / ax_tree.

Two read-only tools that capture screen state without mutating it.
Still gated through the warden (Tier 0 — read-only but the operator
may still want to allowlist screenshot capture in certain contexts).
"""

from __future__ import annotations

from typing import Any

from selffork_orchestrator.tools.base import (
    ToolArgs,
    ToolContext,
    ToolSpec,
)
from selffork_orchestrator.tools.body._internal import (
    _emit_audit,
    _invoke,
    _require_driver,
)

__all__ = [
    "BodyAxTreeArgs",
    "BodyScreenshotArgs",
    "build_observation_tools",
]


class BodyScreenshotArgs(ToolArgs):
    rect: tuple[int, int, int, int] | None = None


class BodyAxTreeArgs(ToolArgs):
    bundle_id: str | None = None


async def _body_screenshot(
    ctx: ToolContext, args: BodyScreenshotArgs,
) -> dict[str, Any]:
    driver = _require_driver(ctx)

    async def _do() -> dict[str, Any]:
        png = await driver.screenshot(rect=args.rect)
        # Persist via ScreenshotStore (M5 audit-fix wave — ToolContext field).
        ref_path: str | None = None
        store = ctx.screenshot_store
        if store is not None:
            ref = store.write(  # type: ignore[attr-defined]
                png,
                ctx.session_id,
                project_slug=ctx.project_slug,
            )
            ref_path = str(ref.path)
            _emit_audit(
                ctx,
                "body.observation",
                {
                    "ref_path": ref_path,
                    "bytes_size": len(png),
                },
            )
        return {"bytes_size": len(png), "ref_path": ref_path}

    return await _invoke(
        ctx,
        action_type="screenshot",
        target_uri=None,
        args_summary={"rect": args.rect},
        coro_factory=_do,
    )


async def _body_ax_tree(
    ctx: ToolContext, args: BodyAxTreeArgs,
) -> dict[str, Any]:
    driver = _require_driver(ctx)

    async def _do() -> dict[str, Any]:
        tree = await driver.ax_tree(bundle_id=args.bundle_id)
        node_count = len(tree) if isinstance(tree, list) else 1
        return {"node_count": node_count}

    return await _invoke(
        ctx,
        action_type="ax_tree",
        target_uri=args.bundle_id,
        args_summary={"bundle_id": args.bundle_id},
        coro_factory=_do,
    )


def build_observation_tools() -> list[ToolSpec[Any]]:
    """Two observation tools — screenshot / ax_tree."""
    return [
        ToolSpec(
            name="body_screenshot",
            description=(
                "Capture a PNG screenshot; optionally crop by rect (T0)."
            ),
            args_model=BodyScreenshotArgs,
            handler=_body_screenshot,
        ),
        ToolSpec(
            name="body_ax_tree",
            description=(
                "Dump the accessibility tree of an app or system-wide (T0)."
            ),
            args_model=BodyAxTreeArgs,
            handler=_body_ax_tree,
        ),
    ]
