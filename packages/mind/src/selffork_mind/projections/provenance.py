"""Provenance recorder for Mind retrieval traces.

Per ADR-002 §8. Every time the Mind retriever returns notes for an LLM
context injection, a :class:`ProvenanceEntry` is written to the audit log.
The dashboard (Order 5) shows these as "Sources" — which note, from which
session, contributed to which answer.

Design parallel to :class:`selffork_shared.audit.AuditLogger`: append-only
JSONL, atomic line append, file-per-correlation. Stays out of the
critical retrieval path — recording is async and best-effort (failures
log a warning but never fail the retrieval).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

__all__ = ["ProvenanceEntry", "ProvenanceRecorder"]


@dataclass(frozen=True, slots=True)
class ProvenanceEntry:
    """One row of provenance.

    A single "Mind injected N notes for query Q in session S" event.
    """

    correlation_id: str
    """Round-loop correlation id (orchestrator AuditLogger correlation)."""

    session_id: str
    """Session that asked Mind for memories."""

    project_slug: str | None
    """Project context, if scoped."""

    query: str
    """The retrieval query string."""

    note_ids: tuple[UUID, ...]
    """The notes Mind returned, in score order."""

    scores: tuple[float, ...]
    """Score per note (cosine, rerank, or baseline depending on stage)."""

    retriever: str
    """Identifier for the retriever that produced this result.

    e.g. ``"vector:bge-m3"``, ``"graph:hipporag2"``, ``"hybrid:adaptive"``.
    """

    reranker: str | None = None
    """Reranker that re-scored, if any."""

    ts: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_jsonl(self) -> str:
        """Serialise as one JSONL line (no trailing newline)."""
        payload = {
            "ts": self.ts.isoformat(),
            "correlation_id": self.correlation_id,
            "session_id": self.session_id,
            "project_slug": self.project_slug,
            "query": self.query,
            "note_ids": [str(n) for n in self.note_ids],
            "scores": list(self.scores),
            "retriever": self.retriever,
            "reranker": self.reranker,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class ProvenanceRecorder:
    """Append-only JSONL provenance log.

    Single file per project (or global). Atomic line append via O_APPEND
    flag. Concurrent writers from a single process are serialised through
    an asyncio Lock; cross-process writers should be avoided (one recorder
    per process is the design).
    """

    def __init__(self, *, log_path: Path) -> None:
        self._path = log_path
        self._lock = asyncio.Lock()

    @property
    def log_path(self) -> Path:
        return self._path

    async def record(self, entry: ProvenanceEntry) -> None:
        """Append one entry. Best-effort: log on failure but do not raise."""
        line = entry.to_jsonl() + "\n"
        async with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                # POSIX O_APPEND guarantees atomic line append for short writes.
                fd = os.open(
                    self._path,
                    os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                    0o644,
                )
                try:
                    os.write(fd, line.encode("utf-8"))
                finally:
                    os.close(fd)
            except OSError:
                # Provenance is observability — never fail the retrieval path.
                pass

    async def record_many(self, entries: Sequence[ProvenanceEntry]) -> None:
        """Append a batch of entries."""
        if not entries:
            return
        # Compose into one buffered write so the syscall count stays bounded.
        buffer = "".join(e.to_jsonl() + "\n" for e in entries)
        async with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(
                    self._path,
                    os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                    0o644,
                )
                try:
                    os.write(fd, buffer.encode("utf-8"))
                finally:
                    os.close(fd)
            except OSError:
                pass

    def read_all(self) -> list[ProvenanceEntry]:
        """Read all recorded entries (for tests + dashboard read API).

        Tolerates malformed lines by skipping them silently — a single bad
        write must never poison the whole log.
        """
        if not self._path.is_file():
            return []
        out: list[ProvenanceEntry] = []
        with self._path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                with contextlib.suppress(KeyError, ValueError, TypeError):
                    out.append(_payload_to_entry(payload))
        return out


def _payload_to_entry(payload: dict[str, object]) -> ProvenanceEntry:
    note_ids_raw = payload.get("note_ids", [])
    if not isinstance(note_ids_raw, list):
        raise TypeError("note_ids must be a list")
    scores_raw = payload.get("scores", [])
    if not isinstance(scores_raw, list):
        raise TypeError("scores must be a list")
    ts_raw = payload.get("ts")
    if not isinstance(ts_raw, str):
        raise TypeError("ts must be an ISO string")
    correlation_id = payload.get("correlation_id")
    session_id = payload.get("session_id")
    query = payload.get("query")
    retriever = payload.get("retriever")
    if not (
        isinstance(correlation_id, str)
        and isinstance(session_id, str)
        and isinstance(query, str)
        and isinstance(retriever, str)
    ):
        raise TypeError("required string fields missing or wrong type")
    project_slug = payload.get("project_slug")
    reranker = payload.get("reranker")
    return ProvenanceEntry(
        correlation_id=correlation_id,
        session_id=session_id,
        project_slug=project_slug if isinstance(project_slug, str) else None,
        query=query,
        note_ids=tuple(UUID(str(n)) for n in note_ids_raw),
        scores=tuple(float(s) for s in scores_raw),
        retriever=retriever,
        reranker=reranker if isinstance(reranker, str) else None,
        ts=datetime.fromisoformat(ts_raw),
    )
