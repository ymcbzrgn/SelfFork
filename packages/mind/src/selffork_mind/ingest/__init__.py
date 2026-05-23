"""Heartbeat / structured-source ingest pipelines (ADR-009 §5).

Each ingester reads a deterministic source (no LLM) and writes typed
:class:`~selffork_mind.memory.model.Note` rows to the relevant pool.
"""

from __future__ import annotations

from selffork_mind.ingest.heartbeat import (
    HeartbeatIngester,
    HeartbeatIngestReport,
    IngestCheckpoint,
    audit_entry_to_note,
)

__all__ = [
    "HeartbeatIngestReport",
    "HeartbeatIngester",
    "IngestCheckpoint",
    "audit_entry_to_note",
]
