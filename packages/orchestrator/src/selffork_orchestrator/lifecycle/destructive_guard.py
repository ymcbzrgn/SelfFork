"""Destructive-action guard — Session-layer interception (ADR-006 §4.5).

Before ``Session._run_agent`` calls ``sandbox.exec(cmd, env=env)``, this
helper checks the command against the destructive whitelist. When a
category matches:

1. A :class:`PendingConfirmation` entry is opened in the store.
2. The round-loop **blocks** until the operator approves/cancels OR the
   per-category ``confirm_window_hours`` elapses (silence = cancel,
   fail-safe NO).
3. The result (``GuardDecision``) tells the caller whether to proceed
   with the exec or raise :class:`DestructiveActionBlockedError`.

No-mock contract: this helper does NOT contact Telegram itself. The
store's ``notify_hook`` (wired in S3 Phase E) bridges to the outbound
PTB bridge; the inbound approval flow updates the store via
``/api/pending-confirmations/{id}/approve`` or the PTB CallbackQuery
handler.

The blocking implementation polls the store every
``poll_interval_seconds`` (default 0.5s). 4-hour worst case = 28800
polls — cheap, no busy loop. The trade-off is up to ``poll_interval``
latency between an operator approve and the round-loop resuming;
acceptable for human-scale destructive actions. A signalling-based
refactor (asyncio.Event per entry) is a candidate for ADR-008 S-Auto
when concurrency >1 becomes interesting.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
import time
from collections.abc import Mapping
from pathlib import Path

from selffork_body.sandbox.destructive_whitelist import (
    CandidateAction,
    DestructiveCategory,
    DestructiveWhitelist,
)
from selffork_body.sandbox.pending_confirmations import (
    PendingConfirmation,
    PendingConfirmationStore,
)
from selffork_shared.audit import AuditLogger
from selffork_shared.errors import SelfForkError
from selffork_shared.logging import get_logger

__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "DestructiveActionBlockedError",
    "GuardDecision",
    "check_destructive_action",
    "cmd_to_candidate_action",
]

_log = get_logger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 0.5


class DestructiveActionBlockedError(SelfForkError):
    """Raised when a destructive action is denied (cancelled or expired).

    Carries the entry so the caller can include it in the round-loop
    audit. The orchestrator catches this in ``_run_agent`` and surfaces
    it as a session failure with reason = ``destructive_<status>``.
    """

    def __init__(self, *, reason: str, entry: PendingConfirmation | None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.entry = entry


@dataclasses.dataclass(frozen=True, slots=True)
class GuardDecision:
    """Result of :func:`check_destructive_action`."""

    allow: bool
    reason: str  # "not_destructive" | "approved" | "cancelled" | "expired" | "guard_deadline"
    entry: PendingConfirmation | None = None
    category_id: str | None = None


def cmd_to_candidate_action(
    cmd: list[str],
    env: Mapping[str, str] | None,
) -> CandidateAction:
    """Map a subprocess invocation to a :class:`CandidateAction` shape.

    The whitelist matcher (``destructive_whitelist.MatchRule``) inspects
    ``tool``, ``args``, ``env``, plus SQL/URL/http_method fields. For a
    raw subprocess we can populate ``tool`` and ``args`` (and ``env``);
    SQL/URL detection is wrapper-tool-specific and lives in higher
    layers if/when those wrappers exist.

    ``cmd[0]`` may be an absolute path (``/usr/local/bin/git``) — the
    whitelist matches by basename (``git``), so we strip the directory.
    """
    if not cmd:
        return CandidateAction()
    tool = Path(cmd[0]).name or cmd[0]
    args = tuple(str(a) for a in cmd[1:])
    return CandidateAction(
        tool=tool,
        args=args,
        env=dict(env) if env else {},
    )


_SQL_HINT_RE = re.compile(
    r"\b(DROP\s+TABLE|TRUNCATE|DELETE\s+FROM)\b",
    re.IGNORECASE,
)


def _extract_inline_sql(cmd: list[str]) -> str | None:
    """Best-effort: detect inline SQL passed via ``-c`` / ``-e`` / ``--execute``.

    Whitelist rules using ``sql_keyword`` fire only when CandidateAction.sql
    is populated. CLI agents frequently invoke ``psql -c "DROP TABLE …"``
    inline; this helper surfaces that text so the matcher can catch it.
    """
    for i, token in enumerate(cmd):
        if token in {"-c", "-e", "--execute", "--command"} and i + 1 < len(cmd):
            candidate = cmd[i + 1]
            if _SQL_HINT_RE.search(candidate):
                return candidate
    return None


async def check_destructive_action(
    *,
    cmd: list[str],
    env: Mapping[str, str] | None,
    workspace_slug: str | None,
    whitelist: DestructiveWhitelist,
    store: PendingConfirmationStore,
    audit: AuditLogger,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    max_wait_seconds: float | None = None,
) -> GuardDecision:
    """Block ``cmd`` if it matches a destructive category, else allow.

    Args:
        cmd: Argv list as passed to ``sandbox.exec``.
        env: Process env (or ``None``).
        workspace_slug: Active project slug for the pending entry; ``None``
            for orphan runs (entry is recorded with workspace=None).
        whitelist: Loaded :class:`DestructiveWhitelist` (caller owns the
            instance; cheap to share across rounds).
        store: :class:`PendingConfirmationStore` (typically the same
            instance the dashboard's pending router serves).
        audit: Audit logger; emits ``destructive_action_*`` events.
        poll_interval_seconds: How often to re-check the entry's status.
        max_wait_seconds: Hard ceiling on the wait. ``None`` defers to the
            category's ``confirm_window_hours`` + a small safety margin.

    Returns:
        :class:`GuardDecision` — caller proceeds with exec iff ``allow``.
    """
    action = cmd_to_candidate_action(cmd, env)
    inline_sql = _extract_inline_sql(cmd)
    if inline_sql is not None:
        action = dataclasses.replace(action, sql=inline_sql)

    category = whitelist.match(action)
    if category is None:
        return GuardDecision(allow=True, reason="not_destructive")

    entry = store.request(
        category=category,
        action=action,
        workspace_slug=workspace_slug,
    )
    audit.emit(
        "destructive_action_requested",
        payload={
            "id": entry.id,
            "category": category.id,
            "workspace": workspace_slug,
            "summary": entry.command_summary,
            "window_hours": category.confirm_window_hours,
            "expires_at": entry.expires_at,
        },
    )
    _log.warning(
        "destructive_action_pending",
        confirmation_id=entry.id,
        category=category.id,
        workspace=workspace_slug,
        summary=entry.command_summary,
        expires_at=entry.expires_at,
    )

    final = await _await_decision(
        store=store,
        category=category,
        entry_id=entry.id,
        poll_interval_seconds=poll_interval_seconds,
        max_wait_seconds=max_wait_seconds,
    )

    if final is None:
        # Entry vanished from the store mid-wait (shouldn't happen
        # in-process; defensively treat as cancelled).
        audit.emit(
            "destructive_action_cancelled",
            payload={"id": entry.id, "reason": "vanished"},
        )
        return GuardDecision(
            allow=False,
            reason="cancelled",
            entry=None,
            category_id=category.id,
        )

    if final.status == "approved":
        audit.emit(
            "destructive_action_approved",
            payload={
                "id": final.id,
                "category": category.id,
                "decided_by": final.decided_by,
            },
        )
        return GuardDecision(
            allow=True,
            reason="approved",
            entry=final,
            category_id=category.id,
        )

    if final.status == "expired":
        audit.emit(
            "destructive_action_timeout",
            payload={
                "id": final.id,
                "category": category.id,
                "window_hours": category.confirm_window_hours,
            },
        )
        return GuardDecision(
            allow=False,
            reason="expired",
            entry=final,
            category_id=category.id,
        )

    # status == "cancelled" (or any unexpected non-pending status).
    audit.emit(
        "destructive_action_cancelled",
        payload={
            "id": final.id,
            "category": category.id,
            "decided_by": final.decided_by,
        },
    )
    return GuardDecision(
        allow=False,
        reason="cancelled",
        entry=final,
        category_id=category.id,
    )


async def _await_decision(
    *,
    store: PendingConfirmationStore,
    category: DestructiveCategory,
    entry_id: str,
    poll_interval_seconds: float,
    max_wait_seconds: float | None,
) -> PendingConfirmation | None:
    """Poll until the entry leaves ``pending`` or the window elapses.

    The poll interval is intentionally coarse (default 0.5s) — destructive
    actions are human-scale, sub-second precision is unnecessary, and a
    busy loop on SQLite would waste cycles.
    """
    window_seconds = float(category.confirm_window_hours) * 3600.0
    safety_margin = 5.0  # let ``expire_stale`` flip the entry before we bail.
    deadline = time.monotonic() + (
        max_wait_seconds if max_wait_seconds is not None else window_seconds + safety_margin
    )

    while time.monotonic() < deadline:
        # Trigger the store's own expiry sweep so the window enforces
        # itself without an external scheduler. Cheap (in-memory walk).
        store.expire_stale()
        current = store.get(entry_id)
        if current is None:
            return None
        if current.status != "pending":
            return current
        await asyncio.sleep(poll_interval_seconds)

    # Deadline hit before the entry's window elapsed (only possible
    # when caller passed ``max_wait_seconds`` shorter than the window).
    # An operator may have decided concurrently — re-read after our
    # cancel so a late approve isn't reported as a deny (audit fix #11).
    current = store.get(entry_id)
    if current is not None and current.status != "pending":
        return current
    store.cancel(entry_id, by="guard-deadline")
    return store.get(entry_id)
