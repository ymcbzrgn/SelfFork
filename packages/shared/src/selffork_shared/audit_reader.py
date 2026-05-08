"""Read primitives for SelfFork audit JSONL logs.

Mirror of :mod:`selffork_shared.audit` (the writer). Both pillars consume
audit logs:

- ``selffork_orchestrator.dashboard.audit_reader`` — Pydantic-envelope
  adapter for the FastAPI dashboard.
- ``selffork_mind.memory.tiers.recall`` — Mind T6 tier-aware envelope.

This module owns the on-disk parsing primitives so the parsers don't drift
between consumers. It returns plain ``@dataclass`` records — Pydantic
envelopes belong to the consumer (one per surface).

Tolerance: malformed JSON lines are silently skipped (we'd rather drop one
event than crash a long-running stream).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from selffork_shared.logging import get_logger

__all__ = [
    "RawAuditEvent",
    "SessionSummary",
    "infer_cli_from_binary",
    "iter_session_events",
    "list_audit_files",
    "parse_audit_line",
    "parse_iso_timestamp",
    "summarize_session",
    "tail_session_events",
]

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RawAuditEvent:
    """Plain-dataclass representation of one audit JSONL line.

    Backend-neutral: callers convert to their own Pydantic envelopes if
    they need API-shape validation.
    """

    ts: datetime
    correlation_id: str | None
    session_id: str
    category: str
    level: str
    event: str
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """High-level summary of one audit JSONL file."""

    session_id: str
    started_at: datetime
    last_event_at: datetime
    final_state: str | None
    rounds_observed: int
    cli_agent: str | None
    audit_path: Path


def parse_iso_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; treat trailing ``Z`` as UTC, naive→UTC."""
    s = value
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_audit_line(
    line: str,
    *,
    session_id_hint: str | None = None,
) -> RawAuditEvent | None:
    """Parse one JSONL line; return ``None`` for malformed input.

    ``session_id_hint`` is used when the event JSON omits ``session_id``
    (the writer always emits it; older logs may not).
    """
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    try:
        return RawAuditEvent(
            ts=parse_iso_timestamp(str(obj["ts"])),
            correlation_id=_optional_str(obj.get("correlation_id")),
            session_id=str(obj.get("session_id") or session_id_hint or ""),
            category=str(obj["category"]),
            level=str(obj.get("level", "INFO")),
            event=str(obj["event"]),
            payload=dict(obj.get("payload") or {}),
        )
    except (KeyError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def list_audit_files(audit_dirs: Iterable[Path]) -> list[Path]:
    """List ``*.jsonl`` files across one or more dirs, sorted by mtime DESC."""
    out: list[Path] = []
    for d in audit_dirs:
        if not d.is_dir():
            continue
        out.extend(p for p in d.iterdir() if p.is_file() and p.suffix == ".jsonl")
    out.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return out


def iter_session_events(path: Path) -> Iterator[RawAuditEvent]:
    """Yield every parseable event in one session file. Empty if file missing."""
    if not path.is_file():
        return
    session_id = path.stem
    with path.open(encoding="utf-8") as f:
        for line in f:
            ev = parse_audit_line(line, session_id_hint=session_id)
            if ev is not None:
                yield ev


async def tail_session_events(
    path: Path,
    *,
    poll_interval_seconds: float = 0.5,
) -> AsyncIterator[RawAuditEvent]:
    """``tail -F``-style streaming.

    Phase 1: wait for the file to appear (poll). Phase 2: drain the existing
    contents. Phase 3: keep the handle open and poll for appends. The caller
    cancels by closing the surrounding task; we propagate ``CancelledError``
    so file handles are released.
    """
    while not path.is_file():  # noqa: ASYNC110, ASYNC240 — polling stat is the design (see docstring)
        await asyncio.sleep(poll_interval_seconds)

    session_id = path.stem
    with path.open(encoding="utf-8") as f:
        for line in f:
            ev = parse_audit_line(line, session_id_hint=session_id)
            if ev is not None:
                yield ev

        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(poll_interval_seconds)
                continue
            ev = parse_audit_line(line, session_id_hint=session_id)
            if ev is not None:
                yield ev


def infer_cli_from_binary(binary_path: str) -> str | None:
    """Map a binary path/name to the canonical CLI agent identifier.

    Recognised: ``opencode``, ``claude``, ``gemini``, ``codex``. Anything
    else returns ``None`` (no fabrication).
    """
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


def summarize_session(path: Path) -> SessionSummary | None:
    """Walk one audit JSONL and produce a high-level summary.

    Returns ``None`` if the file holds zero parseable events.
    """
    started_at: datetime | None = None
    last_at: datetime | None = None
    final_state: str | None = None
    rounds = 0
    cli_agent: str | None = None

    for ev in iter_session_events(path):
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
                    cli_agent = infer_cli_from_binary(binary)
        elif ev.category == "sandbox.exec" and cli_agent is None:
            cmd = ev.payload.get("command")
            if isinstance(cmd, list) and cmd and isinstance(cmd[0], str):
                cli_agent = infer_cli_from_binary(cmd[0])

    if started_at is None or last_at is None:
        return None
    return SessionSummary(
        session_id=path.stem,
        started_at=started_at,
        last_event_at=last_at,
        final_state=final_state,
        rounds_observed=rounds,
        cli_agent=cli_agent,
        audit_path=path,
    )
