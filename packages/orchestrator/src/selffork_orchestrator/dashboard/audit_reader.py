"""Dashboard adapter over :mod:`selffork_shared.audit_reader`.

Translates the shared dataclass primitives into the FastAPI Pydantic
envelopes (:class:`AuditEvent`, :class:`RecentSession`) the dashboard
returns to its clients. Tail behaviour, malformed-line tolerance, mtime
sort, multi-dir merge — all delegated to the shared module so the parser
behaviour stays consistent with Mind T6.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from pathlib import Path

from selffork_orchestrator.dashboard.schemas import (
    AuditEvent,
    RecentSession,
)
from selffork_shared.audit_reader import (
    RawAuditEvent,
    SessionSummary,
    iter_session_events,
    list_audit_files,
    summarize_session,
)
from selffork_shared.audit_reader import (
    tail_session_events as _shared_tail_session_events,
)

__all__ = [
    "list_recent_sessions",
    "read_session_events",
    "tail_session_events",
]


def list_recent_sessions(
    audit_dirs: Iterable[Path],
    *,
    limit: int = 50,
) -> list[RecentSession]:
    """List sessions across one or more audit dirs, sorted by mtime DESC."""
    files = list_audit_files(audit_dirs)
    out: list[RecentSession] = []
    for path in files[:limit]:
        try:
            summary = summarize_session(path)
        except OSError:
            continue
        if summary is not None:
            out.append(_summary_to_response(summary))
    return out


def read_session_events(
    audit_dir: Path,
    session_id: str,
) -> list[AuditEvent]:
    """Read all events for one session. Empty list if file missing."""
    path = audit_dir / f"{session_id}.jsonl"
    return [_event_to_response(ev) for ev in iter_session_events(path)]


async def tail_session_events(
    audit_dir: Path,
    session_id: str,
    *,
    poll_interval_seconds: float = 0.5,
) -> AsyncIterator[AuditEvent]:
    """Yield events as they're appended to ``<session_id>.jsonl``."""
    path = audit_dir / f"{session_id}.jsonl"
    async for ev in _shared_tail_session_events(
        path,
        poll_interval_seconds=poll_interval_seconds,
    ):
        yield _event_to_response(ev)


def _summary_to_response(s: SessionSummary) -> RecentSession:
    return RecentSession(
        session_id=s.session_id,
        started_at=s.started_at,
        last_event_at=s.last_event_at,
        final_state=s.final_state,
        rounds_observed=s.rounds_observed,
        cli_agent=s.cli_agent,
    )


def _event_to_response(ev: RawAuditEvent) -> AuditEvent:
    return AuditEvent(
        ts=ev.ts,
        category=ev.category,
        level=ev.level,
        event=ev.event,
        payload=ev.payload,
    )
