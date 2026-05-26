"""Body pillar tool helpers — shared by every ``body_*`` handler.

Split out of the original ``tools/body.py`` flat module in S-ToolFleet
Faz 0 hierarchical refactor. The gate / audit / invoke triplet is the
same shape across every action so it lives here, and the per-action
modules (:mod:`interaction`, :mod:`observation`, :mod:`lifecycle`) own
just their args schema + handler + spec factory.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from selffork_orchestrator.tools.base import (
    ToolContext,
    raise_unauthorized,
)

__all__ = [
    "_emit_audit",
    "_gate",
    "_invoke",
    "_require_driver",
]


def _require_driver(ctx: ToolContext) -> Any:
    if ctx.body_driver is None:
        raise_unauthorized(
            "this tool requires an active body driver; start a session with "
            "`selffork run --body <web|android|ios|macos|tmux>`",
        )
        raise AssertionError("unreachable")  # pragma: no cover
    return ctx.body_driver


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
    except Exception:  # noqa: S110 — audit emit failure must not block the action
        pass


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
