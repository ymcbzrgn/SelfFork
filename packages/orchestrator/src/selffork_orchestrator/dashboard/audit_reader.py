"""Read-only helpers for the dashboard's audit-log surface.

The dashboard never writes audit logs — it only consumes them. The
authoritative writer is :class:`selffork_shared.audit.AuditLogger`,
which produces newline-delimited JSON files at ``~/.selffork/audit/``
(or wherever ``audit.audit_dir`` is configured).

Two shapes of consumer:

1. **Snapshot read** — for ``GET /api/sessions/<id>/events`` and the
   "recent sessions" listing. Loads one file from start to end.
2. **Tail-stream** — for the WebSocket. Opens the file, reads to EOF,
   then loops: short sleep, read whatever was appended since. Standard
   ``tail -F`` semantics. Always exits cleanly when the consumer closes
   the WebSocket.

The reader is deliberately tolerant: malformed JSON lines are skipped
with a debug log. We'd rather drop one bad event than crash the UI.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from selffork_orchestrator.dashboard.schemas import (
    AuditEvent,
    RecentSession,
)
from selffork_shared.logging import get_logger

__all__ = [
    "list_recent_sessions",
    "read_session_events",
    "tail_session_events",
]

_log = get_logger(__name__)


def _safe_parse_event(line: str) -> AuditEvent | None:
    """Parse one audit-log line; return ``None`` on malformed input.

    The line format is ``{ts, correlation_id, session_id, category,
    level, event, payload}``; we only surface the subset
    :class:`AuditEvent` cares about.
    """
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    try:
        return AuditEvent(
            ts=_parse_iso(str(obj["ts"])),
            category=str(obj["category"]),
            level=str(obj.get("level", "INFO")),
            event=str(obj["event"]),
            payload=dict(obj.get("payload") or {}),
        )
    except (KeyError, ValueError):
        return None


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def list_recent_sessions(audit_dir: Path, *, limit: int = 50) -> list[RecentSession]:
    """List sessions sorted by file mtime (newest first), capped at ``limit``.

    For each ``<session_id>.jsonl`` file, we open it, read the first
    event for ``started_at``, the last for ``last_event_at`` and any
    terminal state. CLI agent name is recovered from the first
    ``agent.invoke`` event whose payload contains a ``binary``.
    """
    if not audit_dir.is_dir():
        return []
    jsonl_files = [p for p in audit_dir.iterdir() if p.is_file() and p.suffix == ".jsonl"]
    jsonl_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[RecentSession] = []
    for path in jsonl_files[:limit]:
        try:
            summary = _summarize_session_file(path)
        except OSError:
            continue
        if summary is not None:
            out.append(summary)
    return out


def _summarize_session_file(path: Path) -> RecentSession | None:
    """Walk one audit JSONL file and produce a ``RecentSession`` summary."""
    started_at: datetime | None = None
    last_at: datetime | None = None
    final_state: str | None = None
    rounds = 0
    cli_agent: str | None = None

    with path.open(encoding="utf-8") as f:
        for line in f:
            ev = _safe_parse_event(line)
            if ev is None:
                continue
            if started_at is None:
                started_at = ev.ts
            last_at = ev.ts
            if ev.category == "session.state":
                state = ev.payload.get("to") or ev.payload.get("state")
                if isinstance(state, str):
                    final_state = state
            elif ev.category == "agent.invoke":
                rounds += 1
                if cli_agent is None:
                    binary = ev.payload.get("binary")
                    if isinstance(binary, str):
                        cli_agent = _infer_cli_from_binary(binary)
            elif ev.category == "sandbox.exec" and cli_agent is None:
                # Round-loop architecture surfaces the CLI binary via
                # sandbox.exec rather than agent.invoke for some events
                # (the binary is the first element of ``command``).
                cmd = ev.payload.get("command")
                if isinstance(cmd, list) and cmd and isinstance(cmd[0], str):
                    cli_agent = _infer_cli_from_binary(cmd[0])

    if started_at is None or last_at is None:
        return None
    return RecentSession(
        session_id=path.stem,
        started_at=started_at,
        last_event_at=last_at,
        final_state=final_state,
        rounds_observed=rounds,
        cli_agent=cli_agent,
    )


def _infer_cli_from_binary(binary_path: str) -> str | None:
    name = binary_path.rsplit("/", 1)[-1].lower()
    if name == "opencode":
        return "opencode"
    if name == "claude":
        return "claude-code"
    if name == "gemini":
        return "gemini-cli"
    if name == "codex":
        return "codex"
    return None


def read_session_events(
    audit_dir: Path,
    session_id: str,
) -> list[AuditEvent]:
    """Read all events for one session. Empty list if file missing."""
    path = audit_dir / f"{session_id}.jsonl"
    if not path.is_file():
        return []
    out: list[AuditEvent] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            ev = _safe_parse_event(line)
            if ev is not None:
                out.append(ev)
    return out


async def tail_session_events(
    audit_dir: Path,
    session_id: str,
    *,
    poll_interval_seconds: float = 0.5,
) -> AsyncIterator[AuditEvent]:
    """Yield events as they're appended to ``<session_id>.jsonl``.

    Strategy: open the file in text mode, ``tell()`` after the initial
    drain, then loop sleep+read. If the file doesn't exist yet we still
    poll for it (sessions started after the WebSocket opened are valid).

    Cancellation: the caller (FastAPI WebSocket handler) cancels the
    enclosing task when the client disconnects; we propagate
    ``asyncio.CancelledError`` so file handles are released.
    """
    path = audit_dir / f"{session_id}.jsonl"

    # Phase 1: wait for the file to appear (could already exist).
    # Polling is correct here — the file appears via filesystem mtime,
    # not via an in-process event. ``asyncio.Event`` would require us
    # to wire a watchdog elsewhere; sleep+stat is fine for ~0.5s ticks.
    while not path.is_file():  # noqa: ASYNC110 — see docstring rationale
        await asyncio.sleep(poll_interval_seconds)

    # Phase 2: drain everything currently in the file.
    with path.open(encoding="utf-8") as f:
        for line in f:
            ev = _safe_parse_event(line)
            if ev is not None:
                yield ev

        # Phase 3: tail. We're already at EOF; keep the handle open and
        # poll for new lines. ``readline()`` returns "" at EOF, which
        # is our cue to sleep.
        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(poll_interval_seconds)
                continue
            ev = _safe_parse_event(line)
            if ev is not None:
                yield ev
