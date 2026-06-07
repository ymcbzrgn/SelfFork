"""Jr autopilot — session-level metadata + lifecycle tools.

- ``session_state``: snapshot the orchestrator's view of the active session
- ``mark_done``: emit the [SELFFORK:DONE] sentinel (round-loop driver scans it)
- ``cancel_pending``: revoke a previously-emitted act-tool decision
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec

__all__ = ["DONE_SENTINEL", "build_session_tools"]

# Identical literal across all CLIAgents (project_done_sentinel_protocol).
DONE_SENTINEL = "[SELFFORK:DONE]"


# ── session_state ──────────────────────────────────────────────────────────────


class _SessionStateArgs(ToolArgs):
    """No args. Returns the orchestrator's view of the active session."""


def _session_state_handler(
    ctx: ToolContext,
    _args: _SessionStateArgs,
) -> dict[str, Any]:
    return {
        "session_id": ctx.session_id,
        "project_slug": ctx.project_slug,
        "active_cli": ctx.cli_agent_name,
        "mind_enabled": (
            ctx.mind_store is not None
            and ctx.mind_retriever is not None
            and ctx.episodic_writer is not None
        ),
        "proactive_quota_wired": ctx.proactive_reader is not None,
        "launchd_wired": ctx.launchd_scheduler is not None,
    }


# ── mark_done ─────────────────────────────────────────────────────────────────


class _MarkDoneArgs(ToolArgs):
    """Args for ``mark_done``."""

    reason: str = Field(default="", max_length=400)


def _mark_done_handler(
    ctx: ToolContext,
    args: _MarkDoneArgs,
) -> dict[str, Any]:
    # Returning the literal sentinel lets the round-loop driver normalize
    # done detection across CLI agents (each CLIAgent's
    # ``is_selffork_jr_done`` matches the same string).
    return {
        "sentinel": DONE_SENTINEL,
        "reason": args.reason,
        "session_id": ctx.session_id,
    }


# ── cancel_pending ────────────────────────────────────────────────────────────


class _CancelPendingArgs(ToolArgs):
    """Args for ``cancel_pending``."""

    action_id: str = Field(
        ...,
        min_length=1,
        description="Token returned by a prior act-tool (typically a session_id).",
    )
    reason: str = Field(default="", max_length=400)


def _cancel_pending_handler(
    ctx: ToolContext,
    args: _CancelPendingArgs,
) -> dict[str, Any]:
    # M3 cancel surface: launchd plist removal is the only actionable revoke
    # we can do from the tool layer right now (sleep_until installed it).
    # rotate_to / notify_telegram cancellation is the round-loop driver's
    # bookkeeping job — the audit trail captures the intent here so Order 9
    # can wire the rest.
    scheduler = ctx.launchd_scheduler
    cancelled_plist = False
    if scheduler is not None and hasattr(scheduler, "uninstall"):
        try:
            cancelled_plist = bool(scheduler.uninstall(args.action_id))
        except Exception:
            cancelled_plist = False
    return {
        "action_id": args.action_id,
        "reason": args.reason,
        "cancelled_plist": cancelled_plist,
        "session_id": ctx.session_id,
    }


# ── Registry helper ────────────────────────────────────────────────────────────


def build_session_tools() -> list[ToolSpec[Any]]:
    """Return the canonical session-lifecycle tools."""
    return [
        ToolSpec(
            name="session_state",
            description=(
                "Read the orchestrator's view of the active session: "
                "session_id, project_slug, active CLI, and which subsystems "
                "are wired (mind / proactive quota / launchd). Use to remind "
                "yourself of context before deciding the next step."
            ),
            args_model=_SessionStateArgs,
            handler=_session_state_handler,
        ),
        ToolSpec(
            name="mark_done",
            description=(
                "Signal that the operator's PRD is fully delivered. Emits "
                f"the {DONE_SENTINEL} sentinel, which the round-loop driver "
                "uses to stop the loop. ONLY call after every PRD criterion "
                "is verified in code."
            ),
            args_model=_MarkDoneArgs,
            handler=_mark_done_handler,
        ),
        ToolSpec(
            name="cancel_pending",
            description=(
                "Revoke a previously-emitted act-tool decision (e.g. "
                "sleep_until, rotate_to). Pass the action_id returned by "
                "the original tool call (typically a session_id)."
            ),
            args_model=_CancelPendingArgs,
            handler=_cancel_pending_handler,
        ),
    ]
