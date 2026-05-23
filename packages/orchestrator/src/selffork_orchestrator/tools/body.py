"""Body pillar tool surface for Jr autopilot (M5 — ADR-005 §M5-G).

Ten ``body_*`` tools that wire SelfFork Jr's MCP-style call protocol to the
:class:`PermissionWarden` + driver layer. Every handler:

1. Resolves the active body driver from :class:`ToolContext`; refuses with
   ``unauthorized`` when missing (legacy text-only round-loop).
2. Builds a :class:`PermissionRequest` with the action's tier and routes
   through the warden — denial returns a structured ``denied`` result.
3. Executes the driver call, stamps duration_ms / status into audit-friendly
   payload. Exceptions are caught and surfaced as ``handler_error``.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import (
    ToolArgs,
    ToolContext,
    ToolSpec,
    raise_unauthorized,
)

__all__ = [
    "BodyAppLaunchArgs",
    "BodyAxTreeArgs",
    "BodyClickArgs",
    "BodyPressKeyArgs",
    "BodyScreenshotArgs",
    "BodyScrollArgs",
    "BodyStorageStateLoadArgs",
    "BodyStorageStateSaveArgs",
    "BodySwipeArgs",
    "BodyTypeArgs",
    "build_body_tools",
]


# ---------------------------------------------------------------------------
# Args models
# ---------------------------------------------------------------------------


class BodyClickArgs(ToolArgs):
    target: str = Field(min_length=1, description="Element selector or natural-language description")
    bbox: tuple[int, int, int, int] | None = None
    button: Literal["left", "right"] = "left"


class BodyTypeArgs(ToolArgs):
    text: str
    target: str | None = None


class BodyScreenshotArgs(ToolArgs):
    rect: tuple[int, int, int, int] | None = None


class BodyScrollArgs(ToolArgs):
    direction: Literal["up", "down", "top", "bottom", "left", "right"] = "down"
    amount: int = Field(default=300, ge=10, le=10000)


class BodySwipeArgs(ToolArgs):
    start_x: int = Field(ge=0)
    start_y: int = Field(ge=0)
    end_x: int = Field(ge=0)
    end_y: int = Field(ge=0)
    duration_ms: int = Field(default=250, ge=50, le=5000)


class BodyAppLaunchArgs(ToolArgs):
    bundle_id: str = Field(min_length=1)


class BodyPressKeyArgs(ToolArgs):
    key_combo: str = Field(min_length=1, max_length=64)


class BodyStorageStateSaveArgs(ToolArgs):
    provider: str = Field(min_length=1, max_length=64)
    project_slug: str | None = None


class BodyStorageStateLoadArgs(ToolArgs):
    provider: str = Field(min_length=1, max_length=64)
    project_slug: str | None = None


class BodyAxTreeArgs(ToolArgs):
    bundle_id: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_driver(ctx: ToolContext) -> Any:
    if ctx.body_driver is None:
        raise_unauthorized(
            "this tool requires an active body driver; start a session with "
            "`selffork run --body <web|android|ios|macos|tmux>`",
        )
        raise AssertionError("unreachable")  # pragma: no cover
    return ctx.body_driver


async def _gate(
    ctx: ToolContext,
    *,
    action_type: str,
    target_uri: str | None,
    args_summary: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    """Run the warden gate. Returns ``(approved, denied_payload)``.

    **Default-deny when warden missing** (M5 audit-fix wave): if the active
    ``ToolContext`` has no ``permission_warden`` wired, the gate refuses the
    call rather than silently passing through. Dev / test paths that need to
    bypass the warden must construct a ``PermissionWarden(mode=DANGER_FULL_ACCESS)``
    explicitly — silent bypass is a security regression.
    """
    if ctx.permission_warden is None:
        _emit_audit(
            ctx,
            "body.permission.deny",
            {
                "action_type": action_type,
                "target_uri_redacted": target_uri,
                "reason": "no_warden_wired",
                "warden_decision": "deny",
            },
        )
        return False, {
            "status": "denied",
            "decision": "deny",
            "reason": "no_warden_wired",
            "decided_by": "warden",
        }
    from selffork_body.sandbox import build_request

    warden = ctx.permission_warden
    request = build_request(
        request_id=f"req-{uuid.uuid4().hex[:12]}",
        session_id=ctx.session_id,
        action_type=action_type,
        target_uri=target_uri,
        args_summary=args_summary,
    )
    _emit_audit(
        ctx,
        "body.permission.requested",
        {
            "request_id": request.request_id,
            "action_type": action_type,
            "target_uri_redacted": target_uri,
            "risk_tier": request.risk_tier,
        },
    )
    decision = await warden.request(request)  # type: ignore[attr-defined]
    if decision.approved:
        return True, {}
    _emit_audit(
        ctx,
        "body.permission.deny",
        {
            "request_id": request.request_id,
            "action_type": action_type,
            "target_uri_redacted": target_uri,
            "reason": decision.reason,
            "warden_decision": decision.decision,
        },
    )
    return False, {
        "status": "denied",
        "decision": decision.decision,
        "reason": decision.reason,
        "decided_by": decision.decided_by,
    }


def _emit_audit(ctx: ToolContext, category: str, payload: dict[str, Any]) -> None:
    """Best-effort body.* audit emit through ToolContext.audit_logger.

    Silent no-op when the logger isn't wired. ``payload`` may include
    ``risk_tier``, ``action_type``, ``target_uri_redacted``, etc. — caller's
    responsibility to keep keys consistent with AuditCategory contract.
    """
    logger = getattr(ctx, "audit_logger", None)
    if logger is None:
        return
    try:
        emit = getattr(logger, "emit", None)
        if emit is None:
            return
        emit(category, payload=payload)
    except Exception:  # noqa: BLE001 — audit failure must not block the action
        pass


async def _invoke(
    ctx: ToolContext,
    *,
    action_type: str,
    target_uri: str | None,
    args_summary: dict[str, Any],
    coro_factory: Callable[[], Awaitable[Any]],
) -> dict[str, Any]:
    """Common wrapper: gate → execute → audit-friendly result.

    ``coro_factory`` returns the awaitable that calls the driver. Kept as a
    callable so the gate runs before the driver is touched.
    """
    approved, denied = await _gate(
        ctx,
        action_type=action_type,
        target_uri=target_uri,
        args_summary=args_summary,
    )
    if not approved:
        return denied
    _emit_audit(
        ctx,
        "body.action.invoke",
        {"action_type": action_type, "target_uri_redacted": target_uri},
    )
    started = time.monotonic()
    try:
        result = await coro_factory()
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        _emit_audit(
            ctx,
            "body.action.failed",
            {
                "action_type": action_type,
                "exception": exc.__class__.__name__,
                "message": str(exc),
                "duration_ms": duration_ms,
            },
        )
        return {
            "status": "error",
            "exception": exc.__class__.__name__,
            "message": str(exc),
            "duration_ms": duration_ms,
        }
    duration_ms = int((time.monotonic() - started) * 1000)
    out: dict[str, Any] = {
        "status": "ok",
        "duration_ms": duration_ms,
    }
    if isinstance(result, dict):
        out["result"] = result
    elif isinstance(result, (bytes, bytearray)):
        out["bytes_size"] = len(result)
    elif result is not None:
        out["result"] = repr(result)[:200]
    _emit_audit(
        ctx,
        "body.action.executed",
        {
            "action_type": action_type,
            "target_uri_redacted": target_uri,
            "duration_ms": duration_ms,
        },
    )
    return out


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _body_click(ctx: ToolContext, args: BodyClickArgs) -> dict[str, Any]:
    driver = _require_driver(ctx)
    return await _invoke(
        ctx,
        action_type="click",
        target_uri=args.target,
        args_summary={"bbox": args.bbox, "button": args.button},
        coro_factory=lambda: driver.click(args.target, bbox=args.bbox, button=args.button),
    )


async def _body_type(ctx: ToolContext, args: BodyTypeArgs) -> dict[str, Any]:
    driver = _require_driver(ctx)
    return await _invoke(
        ctx,
        action_type="type",
        target_uri=args.target,
        args_summary={"text_len": len(args.text)},
        coro_factory=lambda: driver.type_text(args.text, target=args.target),
    )


async def _body_screenshot(ctx: ToolContext, args: BodyScreenshotArgs) -> dict[str, Any]:
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


async def _body_scroll(ctx: ToolContext, args: BodyScrollArgs) -> dict[str, Any]:
    driver = _require_driver(ctx)
    return await _invoke(
        ctx,
        action_type="scroll",
        target_uri=None,
        args_summary={"direction": args.direction, "amount": args.amount},
        coro_factory=lambda: driver.scroll(direction=args.direction, amount=args.amount),
    )


async def _body_swipe(ctx: ToolContext, args: BodySwipeArgs) -> dict[str, Any]:
    driver = _require_driver(ctx)
    return await _invoke(
        ctx,
        action_type="swipe",
        target_uri=None,
        args_summary={
            "start": (args.start_x, args.start_y),
            "end": (args.end_x, args.end_y),
            "duration_ms": args.duration_ms,
        },
        coro_factory=lambda: driver.swipe(
            args.start_x,
            args.start_y,
            args.end_x,
            args.end_y,
            duration_ms=args.duration_ms,
        ),
    )


async def _body_app_launch(ctx: ToolContext, args: BodyAppLaunchArgs) -> dict[str, Any]:
    driver = _require_driver(ctx)
    return await _invoke(
        ctx,
        action_type="app_launch",
        target_uri=args.bundle_id,
        args_summary={"bundle_id": args.bundle_id},
        coro_factory=lambda: driver.app_launch(args.bundle_id),
    )


async def _body_press_key(ctx: ToolContext, args: BodyPressKeyArgs) -> dict[str, Any]:
    driver = _require_driver(ctx)
    return await _invoke(
        ctx,
        action_type="press_key",
        target_uri=None,
        args_summary={"key_combo": args.key_combo},
        coro_factory=lambda: driver.press_key(args.key_combo),
    )


async def _body_storage_state_save(
    ctx: ToolContext, args: BodyStorageStateSaveArgs
) -> dict[str, Any]:
    driver = _require_driver(ctx)
    project = args.project_slug or ctx.project_slug

    async def _do() -> dict[str, Any]:
        result = await driver.storage_state_save(
            provider=args.provider, project_slug=project
        )
        return {"path": str(result)} if result is not None else {}

    return await _invoke(
        ctx,
        action_type="storage_state_save",
        target_uri=args.provider,
        args_summary={"provider": args.provider, "project_slug": project},
        coro_factory=_do,
    )


async def _body_storage_state_load(
    ctx: ToolContext, args: BodyStorageStateLoadArgs
) -> dict[str, Any]:
    driver = _require_driver(ctx)
    project = args.project_slug or ctx.project_slug

    async def _do() -> dict[str, Any]:
        result = await driver.storage_state_load(
            provider=args.provider, project_slug=project
        )
        return {"loaded": bool(result)}

    return await _invoke(
        ctx,
        action_type="storage_state_load",
        target_uri=args.provider,
        args_summary={"provider": args.provider, "project_slug": project},
        coro_factory=_do,
    )


async def _body_ax_tree(ctx: ToolContext, args: BodyAxTreeArgs) -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_body_tools() -> list[ToolSpec[Any]]:
    """Return the canonical 10-tool body surface for the default registry."""
    return [
        ToolSpec(
            name="body_click",
            description="Click on a UI element via vision/AX-tree locator (T1).",
            args_model=BodyClickArgs,
            handler=_body_click,
        ),
        ToolSpec(
            name="body_type",
            description="Type text into the active or specified target field (T1).",
            args_model=BodyTypeArgs,
            handler=_body_type,
        ),
        ToolSpec(
            name="body_screenshot",
            description="Capture a PNG screenshot; optionally crop by rect (T0).",
            args_model=BodyScreenshotArgs,
            handler=_body_screenshot,
        ),
        ToolSpec(
            name="body_scroll",
            description="Scroll the active surface by direction + amount (T0).",
            args_model=BodyScrollArgs,
            handler=_body_scroll,
        ),
        ToolSpec(
            name="body_swipe",
            description="Swipe gesture between two points with duration (T1).",
            args_model=BodySwipeArgs,
            handler=_body_swipe,
        ),
        ToolSpec(
            name="body_app_launch",
            description="Launch a native app by bundle/package id (T2).",
            args_model=BodyAppLaunchArgs,
            handler=_body_app_launch,
        ),
        ToolSpec(
            name="body_press_key",
            description="Press a key combination such as 'cmd+t' or 'back' (T1).",
            args_model=BodyPressKeyArgs,
            handler=_body_press_key,
        ),
        ToolSpec(
            name="body_storage_state_save",
            description="Persist provider auth storage_state for later sessions (T1).",
            args_model=BodyStorageStateSaveArgs,
            handler=_body_storage_state_save,
        ),
        ToolSpec(
            name="body_storage_state_load",
            description="Load a previously saved provider storage_state (T1).",
            args_model=BodyStorageStateLoadArgs,
            handler=_body_storage_state_load,
        ),
        ToolSpec(
            name="body_ax_tree",
            description="Dump the accessibility tree of an app or system-wide (T0).",
            args_model=BodyAxTreeArgs,
            handler=_body_ax_tree,
        ),
    ]
