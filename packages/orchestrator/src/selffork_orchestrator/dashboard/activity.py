"""Activity-feed aggregator — ``GET /api/activity`` (S8, ADR-007 §4 S8).

Merges four *real* sources into one chronological feed for the dashboard
hero card. There is no mock data anywhere: every row derives from an
artifact that already exists on disk or in process memory, and an empty
system produces an empty feed (``feedback_no_mvp_full_quality_first_time``).

Sources:

1. **Session audit JSONL** — the orphan ``<audit_dir>`` plus every
   ``<projects_root>/<slug>/audit/`` dir. One pass per file yields:
   * a ``session_started`` row (first event) and, when the file reached a
     terminal state, a ``session_ended`` row (last event);
   * per-event rows for the categories in :data:`_CATEGORY_TO_KIND`
     (tool calls, structured Q/A, destructive confirmations).
2. **Heartbeat audit JSONL** — ``<audit_dir>/../heartbeat/audit.jsonl``;
   one ``heartbeat_tick`` row per autonomous tick, ``intent`` = the
   model's reasoning (git-context-controller decision-log lift).
3. **Dashboard activity JSONL** — ``<audit_dir>/../activity.jsonl``;
   project mutations (archive / unarchive / pause / resume) appended by
   the dashboard endpoints via :func:`append_dashboard_activity`. A
   sibling of ``audit/`` so it never pollutes ``/api/sessions/recent``.
4. **Telegram activity ring** — the in-memory
   :class:`~selffork_orchestrator.dashboard.telegram_router.TelegramActivityLog`
   snapshot (passed in by the endpoint; ``None`` when the bridge is off).

The merge is a pure function over its inputs (the Telegram snapshot is
plain data) so it is unit-testable without standing up a FastAPI app.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from selffork_orchestrator.dashboard.schemas import ActivityKind, ActivityRow
from selffork_orchestrator.heartbeat.audit import AuditWriter
from selffork_orchestrator.projects.store import ProjectStore
from selffork_shared.audit_reader import (
    RawAuditEvent,
    infer_cli_from_binary,
    iter_session_events,
    list_audit_files,
    parse_iso_timestamp,
)

if TYPE_CHECKING:
    from selffork_orchestrator.dashboard.telegram_router import (
        TelegramActivityResponse,
    )

__all__ = [
    "aggregate_activity",
    "append_dashboard_activity",
    "default_activity_log_path",
    "default_heartbeat_audit_path",
]

_Severity = Literal["info", "warn", "error"]

# Bound the file walk so a long-lived install with thousands of session
# logs never turns the feed into an O(all-history) scan. The feed is a
# "what happened recently" surface; mtime-DESC ordering means the newest
# files are scanned first, and the per-request ``limit`` (≤ 200) caps the
# rows returned regardless.
_MAX_SESSION_FILES = 120

# Audit categories that become activity rows, mapped to their feed kind.
# Categories NOT here (``session.state`` noise, ``agent.invoke``,
# ``runtime.*``, ``mind.*``, ``body.*``) are intentionally dropped to keep
# the feed signal-high — session lifecycle is surfaced via the
# session_started / session_ended bracket instead of per-state spam.
_CATEGORY_TO_KIND: dict[str, ActivityKind] = {
    "tool.call": "tool_call",
    "tool.structured_question": "tool.structured_question",
    "tool.structured_answer": "tool.structured_answer",
    "destructive_action_requested": "destructive_confirm_requested",
    "destructive_action_extended": "destructive_confirm_requested",
    "destructive_action_approved": "destructive_confirm_resolved",
    "destructive_action_cancelled": "destructive_confirm_resolved",
    "destructive_action_timeout": "destructive_confirm_resolved",
    # Dashboard activity log (project mutations) — category == kind 1:1.
    "project_archived": "project_archived",
    "project_unarchived": "project_unarchived",
    "project_paused": "project_paused",
    "project_resumed": "project_resumed",
}

# A session file whose last ``session.state`` is one of these gets a
# ``session_ended`` row; an in-progress session (running/spawning) does
# not, so the feed never claims a live session finished.
_TERMINAL_STATES: frozenset[str] = frozenset(
    {
        "completed",
        "done",
        "failed",
        "error",
        "stopped",
        "cancelled",
        "paused",
        "paused_rate_limit",
        "paused_auth_required",
    },
)

# Which source can produce which kind — lets an ``event_kind``-filtered
# request skip the sources that can't contribute (e.g. don't read every
# heartbeat tick when the caller only wants ``project_archived``).
_SESSION_KINDS: frozenset[str] = frozenset(
    {
        "session_started",
        "session_ended",
        "tool_call",
        "tool.structured_question",
        "tool.structured_answer",
        "destructive_confirm_requested",
        "destructive_confirm_resolved",
    },
)
_PROJECT_KINDS: frozenset[str] = frozenset(
    {
        "project_archived",
        "project_unarchived",
        "project_paused",
        "project_resumed",
    },
)
_TELEGRAM_KINDS: frozenset[str] = frozenset(
    {"telegram_inbound", "telegram_outbound"},
)


def default_activity_log_path(audit_dir: Path) -> Path:
    """Dashboard activity log: sibling of ``audit/`` so it isn't scanned
    by ``/api/sessions/recent`` (which walks ``audit_dir`` itself)."""
    return audit_dir.parent / "activity.jsonl"


def default_heartbeat_audit_path(audit_dir: Path) -> Path:
    """Heartbeat audit log location relative to the audit root.

    Mirrors :func:`selffork_orchestrator.heartbeat.audit.default_audit_path`
    (``~/.selffork/heartbeat/audit.jsonl``) but derived from ``audit_dir``
    so tests that point ``audit_dir`` at a tmp dir resolve the heartbeat
    log under the same tmp root (no ``$HOME`` dependency)."""
    return audit_dir.parent / "heartbeat" / "audit.jsonl"


def append_dashboard_activity(
    path: Path,
    *,
    category: str,
    summary: str,
    project_slug: str | None,
    payload: dict[str, object] | None = None,
) -> None:
    """Append one dashboard-action row to the activity JSONL.

    Same wire shape as the session audit log (so
    :func:`iter_session_events` parses it) but written from the dashboard
    process for actions that have no owning session — currently the project
    archive / unarchive / pause / resume mutations. Append-only, atomic per
    line. Best-effort: callers wrap in ``contextlib.suppress`` so a feed
    write can never fail the mutation it records.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": _utc_now_iso(),
        "correlation_id": project_slug,
        "session_id": "dashboard",
        "category": category,
        "level": "INFO",
        "event": summary,
        "payload": {**(payload or {}), "project_slug": project_slug},
    }
    line = json.dumps(record, default=str, sort_keys=True, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(line + "\n")


def aggregate_activity(
    *,
    audit_dir: Path,
    projects_root: Path,
    heartbeat_audit_path: Path,
    activity_log_path: Path,
    telegram_activity: TelegramActivityResponse | None = None,
    limit: int = 50,
    since: datetime | None = None,
    before: datetime | None = None,
    project_slug: str | None = None,
    event_kind: str | None = None,
) -> tuple[list[ActivityRow], bool]:
    """Merge all sources into a ts-DESC feed. Returns ``(rows, has_more)``.

    ``limit`` is the page size (the caller caps it to a sane max);
    ``has_more`` is ``True`` when the merge produced more matching rows than
    ``limit``. ``since`` / ``before`` bound the ts window (``since`` also
    short-circuits the file walk via mtime). ``project_slug`` / ``event_kind``
    filter the merged rows.
    """
    rows: list[ActivityRow] = []
    truncated = False

    # Only run a source that can produce the requested ``event_kind`` — a
    # filtered 10s-poll card shouldn't read every heartbeat tick + session
    # file to then throw the rows away.
    if event_kind is None or event_kind in _SESSION_KINDS:
        session_rows, truncated = _rows_from_session_dirs(
            audit_dir=audit_dir,
            projects_root=projects_root,
            since=since,
        )
        rows.extend(session_rows)
    if event_kind is None or event_kind == "heartbeat_tick":
        rows.extend(_rows_from_heartbeat(heartbeat_audit_path))
    if event_kind is None or event_kind in _PROJECT_KINDS:
        rows.extend(_rows_from_activity_log(activity_log_path))
    if event_kind is None or event_kind in _TELEGRAM_KINDS:
        rows.extend(_rows_from_telegram(telegram_activity))

    # Filters (applied after merge so every source is treated uniformly).
    if since is not None:
        rows = [r for r in rows if r.ts >= since]
    if before is not None:
        rows = [r for r in rows if r.ts < before]
    if project_slug is not None:
        rows = [r for r in rows if r.project_slug == project_slug]
    if event_kind is not None:
        rows = [r for r in rows if r.event_kind == event_kind]

    rows.sort(key=lambda r: (r.ts, r.id), reverse=True)
    # ``truncated`` is True when the session-file scan hit ``_MAX_SESSION_FILES``,
    # so the client learns the window is incomplete even when this page isn't
    # full (otherwise a ``since``-bounded window wider than the cap would drop
    # the oldest rows with no signal).
    has_more = truncated or len(rows) > limit
    return rows[:limit], has_more


# ── Source 1: session audit dirs ─────────────────────────────────────────────


def _rows_from_session_dirs(
    *,
    audit_dir: Path,
    projects_root: Path,
    since: datetime | None,
) -> tuple[list[ActivityRow], bool]:
    # Map each audit dir to its project slug in one pass (orphan dir → None).
    project_by_dir: dict[Path, str | None] = {audit_dir: None}
    if projects_root.is_dir():
        store = ProjectStore(root=projects_root)
        for project in store.list_all():
            project_by_dir[store.audit_dir(project.slug)] = project.slug
    audit_dirs = list(project_by_dir)

    out: list[ActivityRow] = []
    files = list_audit_files(audit_dirs)  # mtime DESC
    truncated = len(files) > _MAX_SESSION_FILES
    for path in files[:_MAX_SESSION_FILES]:
        # mtime short-circuit: a file last written before ``since`` holds
        # only older events (audit logs are append-only chronological).
        if since is not None:
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError:
                continue
            if mtime < since:
                continue
        slug = project_by_dir.get(path.parent)
        out.extend(_rows_from_session_file(path, project_slug=slug))
    return out, truncated


def _rows_from_session_file(
    path: Path,
    *,
    project_slug: str | None,
) -> list[ActivityRow]:
    session_id = path.stem
    out: list[ActivityRow] = []
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    final_state: str | None = None
    cli_agent: str | None = None
    local_idx = 0

    for ev in iter_session_events(path):
        if first_ts is None:
            first_ts = ev.ts
        last_ts = ev.ts
        if ev.category == "session.state":
            state = ev.payload.get("to") or ev.payload.get("state")
            if isinstance(state, str):
                final_state = state
        elif ev.category == "agent.invoke" and cli_agent is None:
            binary = ev.payload.get("binary")
            if isinstance(binary, str):
                cli_agent = infer_cli_from_binary(binary)
        kind = _CATEGORY_TO_KIND.get(ev.category)
        if kind is not None:
            out.append(
                _event_row(ev, kind, project_slug=project_slug, local_idx=local_idx),
            )
            local_idx += 1

    if first_ts is not None:
        agent_label = f" ({cli_agent})" if cli_agent else ""
        out.append(
            _make_row(
                ts=first_ts,
                event_kind="session_started",
                summary=f"Session {_short(session_id)} started{agent_label}",
                intent=None,
                project_slug=project_slug,
                session_id=session_id,
                correlation_id=session_id,
                payload={"cli_agent": cli_agent},
                severity="info",
                local_idx=local_idx,
            ),
        )
        local_idx += 1
        if last_ts is not None and final_state in _TERMINAL_STATES:
            out.append(
                _make_row(
                    ts=last_ts,
                    event_kind="session_ended",
                    summary=f"Session {_short(session_id)} ended: {final_state}",
                    intent=None,
                    project_slug=project_slug,
                    session_id=session_id,
                    correlation_id=session_id,
                    payload={"final_state": final_state, "cli_agent": cli_agent},
                    severity="warn" if final_state in {"failed", "error"} else "info",
                    local_idx=local_idx,
                ),
            )
    return out


def _event_row(
    ev: RawAuditEvent,
    kind: ActivityKind,
    *,
    project_slug: str | None,
    local_idx: int,
) -> ActivityRow:
    """Map one mapped-category audit event to an :class:`ActivityRow`."""
    payload = ev.payload
    tool = _str_or_none(payload.get("tool"))
    summary: str
    intent: str | None = None
    severity: _Severity = "info"
    correlation = ev.correlation_id

    if kind == "tool_call":
        summary = f"Tool call: {tool}" if tool else "Tool call"
        correlation = _tool_correlation(ev)
    elif kind == "tool.structured_question":
        summary = f"Structured question: {tool}" if tool else "Structured question"
        correlation = _tool_correlation(ev)
    elif kind == "tool.structured_answer":
        status = _str_or_none(payload.get("status")) or "ok"
        label = f"Structured answer: {tool}" if tool else "Structured answer"
        summary = f"{label} ({status})"
        correlation = _tool_correlation(ev)
    elif kind == "destructive_confirm_requested":
        cmd = (
            _str_or_none(payload.get("command_summary"))
            or _str_or_none(payload.get("command"))
            or _str_or_none(payload.get("category_id"))
        )
        summary = (
            f"Destructive action pending: {cmd}"
            if cmd
            else "Destructive action pending operator approval"
        )
        intent = _str_or_none(payload.get("reason")) or cmd
        severity = "warn"
        correlation = _str_or_none(payload.get("action_id")) or correlation
    elif kind == "destructive_confirm_resolved":
        resolution = ev.category.removeprefix("destructive_action_")
        summary = f"Destructive action {resolution}"
        severity = "warn" if resolution in {"cancelled", "timeout"} else "info"
        correlation = _str_or_none(payload.get("action_id")) or correlation
    else:  # project mutations come through _rows_from_activity_log, not here
        summary = ev.event or kind

    return _make_row(
        ts=ev.ts,
        event_kind=kind,
        summary=summary,
        intent=intent,
        project_slug=project_slug,
        session_id=ev.session_id or None,
        correlation_id=correlation,
        payload=payload,
        severity=severity,
        local_idx=local_idx,
    )


def _tool_correlation(ev: RawAuditEvent) -> str | None:
    """Pair a structured question with its answer: same (session, round,
    order) triple, so the UI can collapse the Q/A into one affordance."""
    rnd = ev.payload.get("round")
    order = ev.payload.get("order")
    if rnd is None or order is None:
        return ev.correlation_id
    return f"{ev.session_id}:{rnd}:{order}"


# ── Source 2: heartbeat audit ────────────────────────────────────────────────


def _rows_from_heartbeat(path: Path) -> list[ActivityRow]:
    out: list[ActivityRow] = []
    writer = AuditWriter(path=path)
    for idx, entry in enumerate(writer.read_all()):
        action = entry.decision_action or entry.result_action or "wait"
        outcome = f" → {entry.result_outcome}" if entry.result_outcome else ""
        out.append(
            _make_row(
                ts=_ensure_utc(entry.timestamp),
                event_kind="heartbeat_tick",
                summary=f"Heartbeat tick #{entry.tick}: {action}{outcome}",
                intent=entry.decision_reasoning,
                project_slug=entry.world_state.get("last_active_workspace")
                if isinstance(entry.world_state, dict)
                else None,
                session_id=None,
                correlation_id=entry.idempotency_key,
                payload={
                    "tick": entry.tick,
                    "trigger": entry.trigger,
                    "decision_action": entry.decision_action,
                    "result_outcome": entry.result_outcome,
                    "result_summary": entry.result_summary,
                    "air_alert": entry.air_alert,
                },
                severity="error" if entry.air_alert else "info",
                local_idx=idx,
            ),
        )
    return out


# ── Source 3: dashboard activity log (project mutations) ─────────────────────


def _rows_from_activity_log(path: Path) -> list[ActivityRow]:
    out: list[ActivityRow] = []
    for idx, ev in enumerate(iter_session_events(path)):
        kind = _CATEGORY_TO_KIND.get(ev.category)
        if kind is None:
            continue
        slug = _str_or_none(ev.payload.get("project_slug")) or ev.correlation_id
        out.append(
            _make_row(
                ts=ev.ts,
                event_kind=kind,
                summary=ev.event or kind,
                intent=None,
                project_slug=slug,
                session_id=None,
                correlation_id=slug,
                payload=ev.payload,
                severity="info",
                local_idx=idx,
            ),
        )
    return out


# ── Source 4: telegram activity ring ─────────────────────────────────────────


def _rows_from_telegram(
    activity: TelegramActivityResponse | None,
) -> list[ActivityRow]:
    if activity is None:
        return []
    out: list[ActivityRow] = []
    for idx, entry in enumerate([*activity.inbound, *activity.outbound]):
        try:
            ts = parse_iso_timestamp(entry.at)
        except (ValueError, TypeError):
            continue
        kind: ActivityKind = (
            "telegram_inbound" if entry.direction == "inbound" else "telegram_outbound"
        )
        out.append(
            _make_row(
                ts=ts,
                event_kind=kind,
                summary=entry.summary,
                intent=entry.detail,
                project_slug=None,
                session_id=None,
                correlation_id=None,
                payload={"direction": entry.direction, "detail": entry.detail},
                severity="info",
                local_idx=idx,
            ),
        )
    return out


# ── Row construction ─────────────────────────────────────────────────────────


def _make_row(
    *,
    ts: datetime,
    event_kind: ActivityKind,
    summary: str,
    intent: str | None,
    project_slug: str | None,
    session_id: str | None,
    correlation_id: str | None,
    payload: dict[str, object],
    severity: _Severity,
    local_idx: int,
) -> ActivityRow:
    ts = _ensure_utc(ts)
    seq_id = int(ts.timestamp() * 1000)
    row_id = f"{session_id or 'sys'}:{event_kind}:{seq_id}:{local_idx}"
    return ActivityRow(
        id=row_id,
        ts=ts,
        seq_id=seq_id,
        event_kind=event_kind,
        summary=summary,
        intent=intent,
        project_slug=project_slug,
        session_id=session_id,
        correlation_id=correlation_id,
        payload=payload,
        severity=severity,
    )


def _ensure_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _short(session_id: str) -> str:
    return session_id[:8] if len(session_id) > 8 else session_id


def _utc_now_iso() -> str:
    raw = datetime.now(UTC).isoformat(timespec="milliseconds")
    return raw.replace("+00:00", "Z")
