"""GitHub tool helpers — gh CLI subprocess + warden gate (no driver requirement).

S-ToolFleet Faz 3. GitHub tools are operator-level / Self-Jr self-commit;
no body driver involved. Uses ``_gate`` for warden + audit shape so the
warden policy + `body.permission.*` audit categories stay consistent.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Awaitable, Callable
from typing import Any

from selffork_orchestrator.tools.base import ToolContext
from selffork_orchestrator.tools.body._internal import _emit_audit, _gate

__all__ = [
    "_invoke_gh",
    "_run_gh",
]


def _gh_path() -> str:
    """Locate the ``gh`` CLI binary or raise."""
    path = shutil.which("gh")
    if path is None:
        raise RuntimeError(
            "gh CLI not found; install via `brew install gh` and authenticate with `gh auth login`",
        )
    return path


async def _run_gh(
    *args: str,
    timeout: float = 60.0,  # noqa: ASYNC109 — propagates to wait_for
) -> dict[str, Any]:
    """Run ``gh <args>`` capturing stdout/stderr. Returns structured result."""
    gh = _gh_path()
    proc = await asyncio.create_subprocess_exec(
        gh,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return {
            "status": "timeout",
            "timeout_seconds": timeout,
            "stdout": "",
            "stderr": "process timed out",
        }
    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "returncode": proc.returncode,
        "stdout": stdout.decode(errors="replace")[:32_768],
        "stderr": stderr.decode(errors="replace")[:8_192],
    }


async def _invoke_gh(
    ctx: ToolContext,
    *,
    action_type: str,
    target_uri: str | None,
    args_summary: dict[str, Any],
    cmd: list[str],
    timeout: float = 60.0,  # noqa: ASYNC109
) -> dict[str, Any]:
    """Run a gh CLI command after warden gate + audit emit."""
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
    result = await _run_gh(*cmd, timeout=timeout)
    _emit_audit(
        ctx,
        "body.action.executed" if result.get("status") == "ok" else "body.action.failed",
        {
            "action_type": action_type,
            "target_uri_redacted": target_uri,
            "returncode": result.get("returncode"),
        },
    )
    return result


async def _invoke_callable(
    ctx: ToolContext,
    *,
    action_type: str,
    target_uri: str | None,
    args_summary: dict[str, Any],
    coro_factory: Callable[[], Awaitable[Any]],
) -> dict[str, Any]:
    """Variant for non-gh callables (still warden-gated)."""
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
    try:
        result = await coro_factory()
    except Exception as exc:
        _emit_audit(
            ctx,
            "body.action.failed",
            {
                "action_type": action_type,
                "exception": exc.__class__.__name__,
                "message": str(exc),
            },
        )
        return {
            "status": "error",
            "exception": exc.__class__.__name__,
            "message": str(exc),
        }
    _emit_audit(
        ctx,
        "body.action.executed",
        {"action_type": action_type, "target_uri_redacted": target_uri},
    )
    if isinstance(result, dict):
        return {"status": "ok", "result": result}
    return {"status": "ok", "result": {"value": repr(result)[:1024]}}
