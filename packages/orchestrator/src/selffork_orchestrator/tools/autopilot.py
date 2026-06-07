"""Jr autopilot — act tools that change orchestrator state.

- ``rotate_to``: request a CLI rotation (consumed by the round-loop driver)
- ``sleep_until``: schedule a launchd wake at the given epoch
- ``notify_telegram``: push to the operator (Order 5 wires the bridge)
- ``compact_context``: trigger a Mind compaction strategy
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.cli_agent.factory import _AGENTS as _CLI_AGENTS
from selffork_orchestrator.resume.cron import LaunchdScheduler, LaunchdSchedulerError
from selffork_orchestrator.resume.store import ScheduledResume, ScheduledResumeStore
from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec

__all__ = ["build_autopilot_tools"]

_VALID_KINDS = ("five_hour", "seven_day", "daily", "per_minute", "rolling", "unknown")


# ── rotate_to ─────────────────────────────────────────────────────────────────


class _RotateToArgs(ToolArgs):
    """Args for ``rotate_to``."""

    cli_id: str = Field(..., min_length=1)
    reason: str = Field(default="", max_length=400)


def _rotate_to_handler(
    ctx: ToolContext,
    args: _RotateToArgs,
) -> dict[str, Any]:
    # Validate against the CLIAgent factory registry — NOT the snapper registry.
    # Snappers can exist for opencode-routed providers (e.g. zai) that are NOT
    # standalone CLI agents; rotating to such a snapper-only id would silently
    # pass here but crash the round-loop driver when it tries to instantiate
    # the agent. Cross-impact noted by Order 4 + 8 audits.
    if args.cli_id not in _CLI_AGENTS:
        return {
            "rotation_requested": False,
            "error": (f"unknown cli_id {args.cli_id!r}; expected one of {sorted(_CLI_AGENTS)}"),
        }
    if args.cli_id == ctx.cli_agent_name:
        return {
            "rotation_requested": False,
            "error": f"already on {args.cli_id!r}; rotation is a no-op",
        }
    # The tool emits a signal; the round-loop driver reads the audit log
    # and performs the actual swap on the next round boundary (Order 9).
    return {
        "rotation_requested": True,
        "from_cli": ctx.cli_agent_name,
        "to_cli": args.cli_id,
        "reason": args.reason,
        "session_id": ctx.session_id,
    }


# ── sleep_until ───────────────────────────────────────────────────────────────


class _SleepUntilArgs(ToolArgs):
    """Args for ``sleep_until``."""

    epoch_seconds: int = Field(..., gt=0, description="UTC Unix epoch seconds.")
    reason: str = Field(default="", max_length=400)
    kind: Literal[
        "five_hour",
        "seven_day",
        "daily",
        "per_minute",
        "rolling",
        "unknown",
    ] = Field(default="unknown")


def _sleep_until_handler(
    ctx: ToolContext,
    args: _SleepUntilArgs,
) -> dict[str, Any]:
    resume_at = datetime.fromtimestamp(args.epoch_seconds, tz=UTC)
    now = datetime.now(tz=UTC)
    if resume_at <= now:
        return {
            "scheduled": False,
            "error": "epoch_seconds is in the past; will not schedule",
        }

    scheduler = ctx.launchd_scheduler
    if not isinstance(scheduler, LaunchdScheduler):
        # Audit-only path: record intent so the round-loop driver (or a
        # future cross-platform scheduler) can act on it.
        return {
            "scheduled": False,
            "reason_no_scheduler": (
                "launchd scheduler not wired (non-macOS host, or scheduler "
                "not injected into ToolContext)"
            ),
            "session_id": ctx.session_id,
            "resume_at_iso": resume_at.isoformat(),
            "kind": args.kind,
        }

    # Fetch the existing paused session's PRD/workspace from the resume
    # store so the launchd-fired ``selffork resume now <sid>`` has the
    # right paths to re-invoke ``selffork run`` against. Without this,
    # the plist would call ``selffork run ""`` and crash on first fire.
    prd_path = ""
    workspace_path = ""
    config_path: str | None = None
    store = ctx.resume_store
    if isinstance(store, ScheduledResumeStore):
        existing = store.load(ctx.session_id)
        if existing is not None:
            prd_path = existing.prd_path
            workspace_path = existing.workspace_path
            config_path = existing.config_path
    if not prd_path:
        return {
            "scheduled": False,
            "error": (
                "no paused ScheduledResume record for "
                f"session_id={ctx.session_id!r}; sleep_until requires the "
                "session to already be in PAUSED_RATE_LIMIT (the round-loop "
                "driver writes the record). Cannot install a plist with an "
                "empty prd_path — launchd would fire `selffork run ''`."
            ),
            "session_id": ctx.session_id,
        }

    record = ScheduledResume(
        session_id=ctx.session_id,
        scheduled_at=now,
        resume_at=resume_at,
        cli_agent=ctx.cli_agent_name or "unknown",
        config_path=config_path,
        prd_path=prd_path,
        workspace_path=workspace_path,
        reason=args.reason or f"sleep_until ({args.kind})",
        kind=args.kind,
    )
    try:
        plist_path = scheduler.install(record)
    except LaunchdSchedulerError as exc:
        return {
            "scheduled": False,
            "error": str(exc),
        }
    return {
        "scheduled": True,
        "session_id": ctx.session_id,
        "plist_path": str(plist_path),
        "resume_at_iso": resume_at.isoformat(),
        "kind": args.kind,
    }


# ── notify_telegram ───────────────────────────────────────────────────────────


class _NotifyTelegramArgs(ToolArgs):
    """Args for ``notify_telegram``."""

    level: Literal["info", "warn", "crit"] = Field(default="info")
    message: str = Field(..., min_length=1, max_length=4000)


def _notify_telegram_handler(
    ctx: ToolContext,
    args: _NotifyTelegramArgs,
) -> dict[str, Any]:
    # Order 5 (Telegram bridge) replaces this stub with a real PTB v22.7
    # call. Until then, the audit log captures the intent so the M7
    # fine-tune dataset still includes operator-style notify decisions.
    return {
        "delivered": False,
        "reason": "Telegram bridge not wired yet (Order 5)",
        "level": args.level,
        "message_preview": args.message[:200],
        "session_id": ctx.session_id,
    }


# ── compact_context ───────────────────────────────────────────────────────────


class _CompactContextArgs(ToolArgs):
    """Args for ``compact_context``."""

    strategy: Literal["summary", "truncate", "handoff"] = Field(default="summary")
    reason: str = Field(default="", max_length=400)


def _compact_context_handler(
    ctx: ToolContext,
    args: _CompactContextArgs,
) -> dict[str, Any]:
    # Compaction strategies live in :mod:`selffork_mind.compaction`
    # (RecencyDecayCompactor, MedoidClusterCompactor, LLMSummaryCompactor)
    # and need a tier-scoped "recent N notes" pull from MindStore. The
    # round-loop driver (Order 9 close-out + Mind list_recent API) wires
    # the actual run; today we record the intent so the M7 fine-tune
    # dataset captures Jr's compaction decisions.
    if ctx.mind_store is None:
        return {
            "compaction_requested": False,
            "strategy": args.strategy,
            "reason": args.reason,
            "session_id": ctx.session_id,
            "deferred": "mind_store not wired in ToolContext",
        }
    return {
        "compaction_requested": True,
        "strategy": args.strategy,
        "reason": args.reason,
        "session_id": ctx.session_id,
        "deferred": ("compactor execution pending MindStore.list_recent + driver wire"),
    }


# ── Registry helper ────────────────────────────────────────────────────────────


def build_autopilot_tools() -> list[ToolSpec[Any]]:
    """Return the canonical Jr autopilot act tools."""
    return [
        ToolSpec(
            name="rotate_to",
            description=(
                "Request a swap to a different CLI agent. The round-loop "
                "driver consumes the request and performs the swap on the "
                "next round boundary. Use when current CLI's quota is "
                "exhausted or when a task is better suited to another CLI."
            ),
            args_model=_RotateToArgs,
            handler=_rotate_to_handler,
        ),
        ToolSpec(
            name="sleep_until",
            description=(
                "Schedule a wake at the given Unix epoch (UTC seconds). On "
                "macOS, installs a launchd plist that fires "
                "`selffork resume now <session_id>` exactly at that moment, "
                "even if the laptop sleeps in between."
            ),
            args_model=_SleepUntilArgs,
            handler=_sleep_until_handler,
        ),
        ToolSpec(
            name="notify_telegram",
            description=(
                "Push a notification to the operator via Telegram. Use "
                "level='crit' only for blocked / awaiting-decision scenarios."
            ),
            args_model=_NotifyTelegramArgs,
            handler=_notify_telegram_handler,
        ),
        ToolSpec(
            name="compact_context",
            description=(
                "Trigger a Mind compaction strategy. 'summary' produces an "
                "LLM digest, 'truncate' drops oldest rounds, 'handoff' "
                "produces a cross-CLI handoff bundle."
            ),
            args_model=_CompactContextArgs,
            handler=_compact_context_handler,
        ),
    ]
