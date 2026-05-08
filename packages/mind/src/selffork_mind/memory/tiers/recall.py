"""T6 Recall — read-only Mind tier over audit JSONL transcripts.

Per ADR-002 §1: T6 is the lowest cognitive memory tier. It does not store
new state; it exposes the existing audit log (the orchestrator's canonical
session record) through a Mind-friendly surface. Higher tiers (T2 Episodic,
T4 Procedural) build on top by writing typed notes alongside.

Wraps :mod:`selffork_shared.audit_reader` primitives with:

- ``StoreScope``-aware filtering (project / session / cli matching).
- Project-slug inference from the audit dir layout
  (``~/.selffork/projects/<slug>/audit/<session>.jsonl`` → ``<slug>``;
  ``~/.selffork/audit/<session>.jsonl`` → ``None`` for orphan).
- Date-range and category filters for per-event queries.

Multiple audit dirs are supported (typically the orphan dir plus every
project's per-project dir). Mtime sort ensures recent sessions surface
first regardless of which dir they came from.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from selffork_mind.store.base import StoreScope
from selffork_shared.audit_reader import (
    RawAuditEvent,
    SessionSummary,
    iter_session_events,
    list_audit_files,
    summarize_session,
    tail_session_events,
)

__all__ = [
    "RecallEvent",
    "RecallReader",
    "RecallSession",
]


_NO_SCOPE = StoreScope()
"""Module-level "no filter" StoreScope; reused as a default arg singleton."""


@dataclass(frozen=True, slots=True)
class RecallEvent:
    """One audit event surfaced through Mind T6.

    Carries the original audit fields plus the resolved ``audit_path``
    (multi-dir reads need this so callers can correlate back to the
    physical file) and the inferred ``project_slug`` (so a Mind retriever
    can scope without a second lookup).
    """

    ts: datetime
    correlation_id: str | None
    session_id: str
    category: str
    level: str
    event: str
    payload: dict[str, object]
    audit_path: Path
    project_slug: str | None


@dataclass(frozen=True, slots=True)
class RecallSession:
    """High-level summary of one session, Mind-tier shape."""

    session_id: str
    started_at: datetime
    last_event_at: datetime
    final_state: str | None
    rounds_observed: int
    cli_agent: str | None
    audit_path: Path
    project_slug: str | None


@dataclass(frozen=True, slots=True)
class _AuditDirs:
    """Materialised tuple of audit dirs (sealed at construction)."""

    dirs: tuple[Path, ...] = field(default_factory=tuple)


class RecallReader:
    """Read-only Mind tier over audit JSONL artefacts.

    Construct once per Mind session; the audit dirs list is sealed at
    construction time. Subsequent reads honour ``StoreScope`` filters
    where applicable.
    """

    def __init__(self, *, audit_dirs: Iterable[Path]) -> None:
        self._dirs = _AuditDirs(dirs=tuple(audit_dirs))

    @property
    def audit_dirs(self) -> tuple[Path, ...]:
        return self._dirs.dirs

    # ── session-level reads ────────────────────────────────────────────

    def list_sessions(
        self,
        *,
        limit: int = 50,
        scope: StoreScope = _NO_SCOPE,
    ) -> list[RecallSession]:
        """List sessions across the configured dirs, mtime DESC.

        Files that fail to summarise (no parseable events, OS error)
        are silently skipped. ``StoreScope`` filters apply on the
        derived :class:`RecallSession` (so e.g. scope by project_slug
        only includes files under that project's audit dir).
        """
        files = list_audit_files(self._dirs.dirs)
        out: list[RecallSession] = []
        for path in files:
            if len(out) >= limit:
                break
            try:
                summary = summarize_session(path)
            except OSError:
                continue
            if summary is None:
                continue
            session = self._summary_to_recall(summary)
            if not _matches_scope(session, scope):
                continue
            out.append(session)
        return out

    def get_session(
        self,
        session_id: str,
        *,
        scope: StoreScope = _NO_SCOPE,
    ) -> RecallSession | None:
        """Fetch one session by id (returns None when missing or out of scope)."""
        path = self._find_audit_path(session_id)
        if path is None:
            return None
        try:
            summary = summarize_session(path)
        except OSError:
            return None
        if summary is None:
            return None
        session = self._summary_to_recall(summary)
        if not _matches_scope(session, scope):
            return None
        return session

    # ── event-level reads ──────────────────────────────────────────────

    def read_session_events(
        self,
        session_id: str,
    ) -> list[RecallEvent]:
        """Snapshot all events for one session. Empty list if missing."""
        path = self._find_audit_path(session_id)
        if path is None:
            return []
        slug = _infer_project_slug(path)
        return [_event_to_recall(ev, path, slug) for ev in iter_session_events(path)]

    async def tail_session_events(
        self,
        session_id: str,
        *,
        poll_interval_seconds: float = 0.5,
    ) -> AsyncIterator[RecallEvent]:
        """``tail -F`` for a single session.

        If the session file does not yet exist in any audit dir, the
        tail is anchored on the first configured dir and waits for the
        file to appear (sessions started after the tail begins are
        valid). When no dirs are configured, raises immediately.
        """
        path = self._find_audit_path(session_id)
        if path is None:
            if not self._dirs.dirs:
                raise ValueError(
                    "RecallReader has no audit dirs; cannot tail",
                )
            path = self._dirs.dirs[0] / f"{session_id}.jsonl"
        slug = _infer_project_slug(path)
        async for ev in tail_session_events(
            path,
            poll_interval_seconds=poll_interval_seconds,
        ):
            yield _event_to_recall(ev, path, slug)

    def query_events(
        self,
        *,
        session_id: str | None = None,
        category: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        scope: StoreScope = _NO_SCOPE,
    ) -> Iterator[RecallEvent]:
        """Stream events filtered by session / category / date range.

        Yields lazily so a long history isn't materialised in memory.
        ``since`` is inclusive; ``until`` is exclusive (half-open
        interval). When ``session_id`` is omitted, every file in every
        configured dir is walked.
        """
        candidate_paths = self._resolve_query_paths(session_id)
        for path in candidate_paths:
            if not path.is_file():
                continue
            try:
                summary = summarize_session(path)
            except OSError:
                continue
            if summary is None:
                continue
            recall_session = self._summary_to_recall(summary)
            if not _matches_scope(recall_session, scope):
                continue
            slug = recall_session.project_slug
            for ev in iter_session_events(path):
                if category is not None and ev.category != category:
                    continue
                if since is not None and ev.ts < since:
                    continue
                if until is not None and ev.ts >= until:
                    continue
                yield _event_to_recall(ev, path, slug)

    # ── helpers ────────────────────────────────────────────────────────

    def _resolve_query_paths(self, session_id: str | None) -> list[Path]:
        if session_id is not None:
            single = self._find_audit_path(session_id)
            return [single] if single is not None else []
        return list_audit_files(self._dirs.dirs)

    def _find_audit_path(self, session_id: str) -> Path | None:
        for d in self._dirs.dirs:
            candidate = d / f"{session_id}.jsonl"
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _summary_to_recall(s: SessionSummary) -> RecallSession:
        return RecallSession(
            session_id=s.session_id,
            started_at=s.started_at,
            last_event_at=s.last_event_at,
            final_state=s.final_state,
            rounds_observed=s.rounds_observed,
            cli_agent=s.cli_agent,
            audit_path=s.audit_path,
            project_slug=_infer_project_slug(s.audit_path),
        )


# ── module helpers ────────────────────────────────────────────────────────


def _event_to_recall(
    ev: RawAuditEvent,
    audit_path: Path,
    project_slug: str | None,
) -> RecallEvent:
    return RecallEvent(
        ts=ev.ts,
        correlation_id=ev.correlation_id,
        session_id=ev.session_id,
        category=ev.category,
        level=ev.level,
        event=ev.event,
        payload=ev.payload,
        audit_path=audit_path,
        project_slug=project_slug,
    )


def _matches_scope(session: RecallSession, scope: StoreScope) -> bool:
    if scope.project_slug is not None and session.project_slug != scope.project_slug:
        return False
    if scope.session_id is not None and session.session_id != scope.session_id:
        return False
    return not (scope.cli_agent is not None and session.cli_agent != scope.cli_agent)


def _infer_project_slug(audit_path: Path) -> str | None:
    """Project slug from the audit dir layout, or None for orphan sessions.

    Per ``project_project_model.md``: per-project audit lives at
    ``~/.selffork/projects/<slug>/audit/<session>.jsonl``. The first
    component named ``projects`` is treated as a sentinel; the next
    component is the slug. Orphan layout
    ``~/.selffork/audit/<session>.jsonl`` returns ``None``.
    """
    parts = audit_path.parts
    try:
        idx = parts.index("projects")
    except ValueError:
        return None
    if idx + 1 >= len(parts):
        return None
    candidate = parts[idx + 1]
    if not candidate or candidate.startswith("."):
        return None
    return candidate
