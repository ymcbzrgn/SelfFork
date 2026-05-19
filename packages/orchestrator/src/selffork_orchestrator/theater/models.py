"""Pydantic domain models for the Live Run Theater event store — S2.

The theater (ADR-007 §4 S2) is the Workspace "Live Run" surface. A
running round-loop produces a single ordered stream of events per
workspace; ordering relies on the monotonic per-workspace ``seq``, never
on ``created_at`` — two events can land in the same millisecond.

S2 ships two event kinds — ``cli_output`` and ``thought``. The third
theater pane, the screenshot timeline, has no producer in S2: the
round-loop is not yet wired to Body vision (ADR-007 §4 S2 scope note),
so no ``screenshot`` event kind exists and that pane renders an honest
empty state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ActiveLoopRecord",
    "CliOutputKind",
    "CliOutputPayload",
    "TheaterEvent",
    "TheaterEventKind",
    "ThoughtPayload",
]


# Event kinds persisted by the store. ``screenshot`` is intentionally
# absent in S2 — see the module docstring.
TheaterEventKind = Literal["cli_output", "thought"]

# CLI output chunk kinds — mirrors
# ``dashboard.theater_router.CLIOutputChunk.kind``.
CliOutputKind = Literal["stdout", "stderr", "system", "jr-prompt", "info"]


class CliOutputPayload(BaseModel):
    """Payload of a ``cli_output`` theater event — one CLI output chunk.

    Produced line-by-line from the round-loop's CLI subprocess stdout /
    stderr. ``jr-prompt`` carries the prompt Self Jr sent to the CLI;
    ``system`` / ``info`` carry round-loop lifecycle notes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: CliOutputKind
    text: str


class ThoughtPayload(BaseModel):
    """Payload of a ``thought`` theater event — a compacted Self Jr thought.

    ``summary`` is the human-readable line shown in the thought bubble —
    plain language, no jargon (the theater is a non-engineer surface).
    ``raw`` is the unfiltered model text, surfaced only behind the
    Settings > Advanced "show raw thinking" toggle.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str
    raw: str | None = None


class TheaterEvent(BaseModel):
    """One event in a workspace's Live Run Theater stream.

    ``seq`` is a per-workspace monotonic counter starting at 1; the
    theater WebSocket tails the stream with ``seq > cursor`` and clients
    order by it, never by ``created_at``. ``payload`` is the kind-specific
    data — a :class:`CliOutputPayload` or :class:`ThoughtPayload` dumped
    to a dict, matching the shape of ``WsEnvelope.payload``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    workspace_slug: str
    session_id: str | None
    seq: int
    kind: TheaterEventKind
    payload: dict[str, object]
    created_at: datetime


class ActiveLoopRecord(BaseModel):
    """Snapshot of one running round-loop — backs ``GET /api/loop/active``.

    Persisted in the theater DB's ``active_loops`` table, not in the
    memory of any one process: a ``selffork run`` process writes its loop
    record and the separate dashboard process reads it. ``updated_at``
    advances every turn; a reader treats a row untouched for too long as
    a crashed loop.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    workspace_slug: str
    workspace_name: str
    cli: str
    turn: int
    started_at: datetime
    updated_at: datetime
    last_thought: str | None = None
