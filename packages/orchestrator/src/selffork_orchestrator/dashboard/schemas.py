"""Pydantic response schemas for the dashboard HTTP API.

Every schema represents a structure that's already on disk somewhere —
we never invent data. The endpoint code reads the real artifact, maps
it into one of these schemas, and returns it.

Per ``project_ui_stack.md`` ABSOLUTE no-mock rule: there's no schema
for any pillar/feature that doesn't yet have a backend artifact.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ActiveBranchPayload",
    "ActivityKind",
    "ActivityResponse",
    "ActivityRow",
    "AuditEvent",
    "BranchResponse",
    "CardCreatePayload",
    "CardMovePayload",
    "CardUpdatePayload",
    "ChatMessageEditPayload",
    "ChatMessagePayload",
    "ChatMessageResponse",
    "ConversationResponse",
    "ConversationThreadResponse",
    "KanbanCardResponse",
    "KanbanResponse",
    "MindNoteCreatePayload",
    "MindNoteUpdatePayload",
    "MindRecallRequestPayload",
    "MindRecallResponse",
    "MindStatsResponse",
    "MindTierStatsRow",
    "NoteResponse",
    "PausedSession",
    "PlanSnapshot",
    "ProjectCreatePayload",
    "ProjectResponse",
    "ProjectUpdatePayload",
    "ProvenanceEntryResponse",
    "RecentSession",
    "RunRequestPayload",
    "RunRequestResponse",
    "TalkCancelResponse",
    "TalkMessageResponse",
    "TalkSendPayload",
    "TalkSendResponse",
    "WorkspaceEntry",
]


class _StrictResponse(BaseModel):
    """Forbid extra fields so accidental drift between schema + audit
    record JSON shapes fails loudly in tests instead of silently."""

    model_config = ConfigDict(extra="forbid")


class PausedSession(_StrictResponse):
    """One row in ``GET /api/sessions/paused``.

    Source-of-truth: a JSON file under ``~/.selffork/scheduled/``
    (one per paused session). See
    :class:`selffork_orchestrator.resume.store.ScheduledResume`.
    """

    session_id: str
    scheduled_at: datetime
    resume_at: datetime
    cli_agent: str
    config_path: str | None
    prd_path: str
    workspace_path: str
    reason: str
    kind: str
    is_due: bool


class RecentSession(_StrictResponse):
    """One row in ``GET /api/sessions/recent``.

    Source-of-truth: ``~/.selffork/audit/<session_id>.jsonl`` mtime,
    last ``session.state`` event in the file, optional ``agent.done``
    or ``error`` markers.
    """

    session_id: str
    started_at: datetime
    last_event_at: datetime
    final_state: str | None  # last observed state, e.g. "completed", "paused_rate_limit"
    rounds_observed: int
    cli_agent: str | None  # parsed from agent.invoke.binary if seen


class AuditEvent(_StrictResponse):
    """One audit-log line, raw."""

    ts: datetime
    category: str
    level: str
    event: str
    payload: dict[str, object]


class PlanSnapshot(_StrictResponse):
    """The current ``.selffork/plan.json`` for one session.

    Source-of-truth: workspace plan-as-state file. Schema mirrors
    :class:`selffork_orchestrator.plan.model.Plan`.
    """

    schema_version: int
    summary: str
    sub_tasks: list[dict[str, object]]


class WorkspaceEntry(_StrictResponse):
    """One node in the per-session workspace file tree."""

    path: str  # relative to workspace root
    kind: str  # "file" | "dir"
    size_bytes: int | None
    modified_at: datetime | None


class RunRequestPayload(BaseModel):
    """Body of ``POST /api/sessions/run``.

    The PRD must already exist on disk; we don't accept inline text in
    MVP (avoids mid-flight file management for the orchestrator).
    """

    prd_path: str
    config_path: str | None = None
    project_slug: str | None = None


class ProjectResponse(_StrictResponse):
    """One row in ``GET /api/projects`` (and the body of ``GET /api/projects/<slug>``)."""

    slug: str
    name: str
    description: str
    root_path: str | None
    created_at: datetime
    updated_at: datetime
    card_counts: dict[str, int]
    # S7 — soft archive + workspace autopilot pause. ``archived_at`` =
    # ``None`` when the project is active; ``autopilot_paused`` = ``True``
    # while Heartbeat is told to skip this workspace.
    archived_at: datetime | None
    autopilot_paused: bool


class ProjectCreatePayload(BaseModel):
    """Body of ``POST /api/projects``. ``slug`` is normalised server-side."""

    name: str
    description: str = ""
    root_path: str | None = None


class ProjectUpdatePayload(BaseModel):
    """Body of ``PUT /api/projects/<slug>``. Omitted fields stay unchanged.

    Note: ``archived_at`` and ``autopilot_paused`` are NOT exposed here —
    they have dedicated POST endpoints (``archive`` / ``unarchive`` and
    ``autopilot/pause`` / ``autopilot/resume``) so each action lands in
    the audit log as a distinct event. ``root_path`` accepts ``""`` to
    clear (omitting leaves the value alone).
    """

    name: str | None = None
    description: str | None = None
    root_path: str | None = None


class KanbanCardResponse(_StrictResponse):
    id: str
    title: str
    body: str
    column: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    last_touched_by_session_id: str | None
    order: int | None


class KanbanResponse(_StrictResponse):
    """Body of ``GET /api/projects/<slug>/kanban``."""

    schema_version: int
    columns: list[str]
    cards_by_column: dict[str, list[KanbanCardResponse]]


class CardCreatePayload(BaseModel):
    title: str
    body: str = ""
    column: str = "backlog"
    order: int | None = None


class CardMovePayload(BaseModel):
    to_column: str


class CardUpdatePayload(BaseModel):
    title: str | None = None
    body: str | None = None
    order: int | None = None


class ProvenanceEntryResponse(_StrictResponse):
    """One row in ``GET /api/projects/<slug>/mind/provenance``.

    Source-of-truth: ``~/.selffork/projects/<slug>/mind/provenance.jsonl``
    (or ``~/.selffork/mind/provenance.jsonl`` for orphan sessions).
    Mirrors :class:`selffork_mind.projections.provenance.ProvenanceEntry`
    flat-shaped so the dashboard's "Sources" surface (CardDetailPanel
    Logs tab) can render without joining.
    """

    ts: datetime
    correlation_id: str
    session_id: str
    project_slug: str | None
    query: str
    note_ids: list[str]
    scores: list[float]
    retriever: str
    reranker: str | None


class RunRequestResponse(_StrictResponse):
    """Response from ``POST /api/sessions/run``.

    The session_id is best-effort — we spawn a subprocess that mints
    its own ULID; we read it back from the spawned audit dir mtime
    once the child has touched its file. ``status="started"`` means
    the subprocess was launched; ``"failed_to_spawn"`` means we
    never got past ``subprocess.Popen``.
    """

    status: str
    pid: int | None
    detail: str | None


# ── Mind HTTP surface — Order 3 ──────────────────────────────────────────────


class NoteResponse(_StrictResponse):
    """One Mind note projected to the wire format.

    UUIDs serialise to strings; timestamps to ISO-8601. Mirrors
    :class:`selffork_mind.memory.model.Note` but flattens private
    schema fields (``identity_fields``) and omits the embedding side
    channel — those belong to the storage layer, not the operator's
    cockpit view.
    """

    id: str
    tier: str
    kind: str
    content: str
    intent: str
    importance: float
    pinned: bool
    project_slug: str | None
    session_id: str | None
    valid_from: datetime
    valid_until: datetime | None
    tag_keys: list[str]
    path_scope: list[str]
    always_apply: bool


class MindTierStatsRow(_StrictResponse):
    count: int
    last_updated: datetime | None


class MindStatsResponse(_StrictResponse):
    """Body of ``GET /api/projects/<slug>/mind/stats``.

    ``tiers`` only includes tiers with at least one currently-valid
    note for the requested scope. UI surfaces decide how to render
    absent tiers (typically: collapsed section with placeholder).
    """

    tiers: dict[str, MindTierStatsRow]


class MindNoteCreatePayload(BaseModel):
    """Body of ``POST /api/projects/<slug>/mind/notes``.

    Fields with no default are required; the others fall back to the
    Note model defaults. Tag pairs are encoded as ``[[k, v], ...]`` so
    the wire format stays JSON-friendly (tuples roundtrip as lists).
    """

    content: str
    tier: str = "episodic"
    kind: str = "observation"
    intent: str = ""
    importance: float = 1.0
    pinned: bool = False
    tag_pairs: list[tuple[str, str]] = []
    session_id: str | None = None


class MindNoteUpdatePayload(BaseModel):
    """Body of ``PATCH /api/projects/<slug>/mind/notes/<id>`` (S7).

    Implements operator-facing in-place edit on top of the Mind T2
    bi-temporal supersede pattern: the endpoint marks the existing
    note ``valid_until=now`` and writes a fresh row with the patched
    fields. All fields optional — omitted fields preserve the
    superseded note's value so the operator can patch ``content``
    alone without re-sending the full record.
    """

    content: str | None = None
    intent: str | None = None
    importance: float | None = None
    pinned: bool | None = None


class MindRecallRequestPayload(BaseModel):
    """Body of ``POST /api/projects/<slug>/mind/recall``.

    A projection of :class:`selffork_mind.store.base.RetrieveConfig` —
    the cockpit doesn't expose every retriever knob; query + tier +
    optional tag-pair predicate covers the M4 Context tab use cases.
    Filter DSL + bi-temporal ``valid_at`` are stretch goals (M5+).
    """

    query: str = ""
    tier: str | None = None
    """Restrict to a single tier; ``None`` queries all tiers."""

    tag_pairs: list[tuple[str, str]] = []
    top_k: int = 20
    threshold: float = 0.0
    session_id: str | None = None


class MindRecallResponse(_StrictResponse):
    """Body of ``POST /api/projects/<slug>/mind/recall``.

    Hits and scores are aligned by index. The cockpit renders both
    arrays as a sorted table; absent fields are an empty list (never
    ``None``) so the UI can iterate without null-guards.
    """

    hits: list[NoteResponse]
    scores: list[float]


# ── Chat surface — Order 4 ──────────────────────────────────────────────────


class BranchResponse(_StrictResponse):
    """One conversation branch projected to the wire format."""

    id: str
    session_id: str
    parent_branch_id: str | None
    fork_message_id: str | None
    label: str
    is_active: bool
    created_at: datetime


class ChatMessageResponse(_StrictResponse):
    """One chat message projected to the wire format."""

    id: str
    branch_id: str
    role: str
    content: str
    parent_message_id: str | None
    created_at: datetime


class ChatMessagePayload(BaseModel):
    """Body of ``POST /api/sessions/<id>/messages``.

    ``branch_id`` is optional — when omitted the message is appended
    to the session's currently-active branch (or to a freshly minted
    ``main`` branch when the session has none yet).
    """

    content: str
    role: str = "user"
    branch_id: str | None = None


class ChatMessageEditPayload(BaseModel):
    """Body of ``POST /api/sessions/<id>/messages/<msg_id>/edit``.

    The edit always creates a *new* branch (assistant-ui semantics —
    edits are immutable; previous branches stay queryable).
    ``branch_label`` defaults to ``alt-<short-uuid>`` server-side.
    """

    content: str
    branch_label: str | None = None


class ActiveBranchPayload(BaseModel):
    """Body of ``PATCH /api/sessions/<id>/active-branch``."""

    branch_id: str


# ── Talk surface — S1 ────────────────────────────────────────────────────────


class ConversationResponse(_StrictResponse):
    """One Talk conversation projected to the wire format."""

    id: str
    workspace_slug: str | None
    title: str
    created_at: datetime
    last_message_at: datetime


class TalkMessageResponse(_StrictResponse):
    """One Talk message projected to the wire format."""

    id: str
    conversation_id: str
    seq: int
    role: str
    content: str
    created_at: datetime


class ConversationThreadResponse(_StrictResponse):
    """Body of ``GET /api/talk/conversations/<id>`` — conversation + thread."""

    conversation: ConversationResponse
    messages: list[TalkMessageResponse]


class TalkSendPayload(BaseModel):
    """Body of ``POST /api/talk/send``.

    ``conversation_id`` continues an existing thread; when omitted a new
    conversation is created (scoped to ``workspace`` when given).
    """

    text: str
    conversation_id: str | None = None
    workspace: str | None = None


class TalkSendResponse(_StrictResponse):
    """Response from ``POST /api/talk/send``.

    Under ADR-011 (S-Stream) the Self Jr reply streams asynchronously over
    the Talk WebSocket; ``POST /send`` returns as soon as the operator
    message persists and the generation task is enqueued — it does NOT
    wait for the reply to land. ``speaker_status`` distinguishes which
    state the cockpit should render:

    * ``"streaming"`` — the operator message persisted, a background
      generation task is now running, and ``generation_id`` is set so the
      cockpit can cancel via ``POST .../cancel-generation/{gid}`` and
      pair the forthcoming ``talk.token`` / ``talk.message`` /
      ``talk.error`` / ``talk.cancelled`` envelopes back to this request.
      ``reply`` is ``None`` (the assistant message arrives over the WS).
    * ``"not_configured"`` — no Speaker endpoint is configured; ``reply``
      is ``None`` and ``generation_id`` is ``None``.

    The historic ``"ok"`` / ``"offline"`` values are no longer produced by
    the streaming path — transport failures arrive as ``talk.error``
    envelopes over the WebSocket instead, so this response can return
    immediately even when the upstream model is wedged.
    """

    conversation_id: str
    operator_message: TalkMessageResponse
    reply: TalkMessageResponse | None
    speaker_status: str
    generation_id: str | None = None


class TalkCancelResponse(_StrictResponse):
    """Response from ``POST /api/talk/conversations/{cid}/cancel-generation``.

    ``cancelled`` is ``True`` when a matching active generation was found
    and signalled to stop; ``False`` when no active task matched (already
    done, never started, or unknown id). ``reason`` carries a short
    human-readable explanation suitable for an honest toast in the
    cockpit (``"cancelled"`` / ``"unknown_generation"`` / ``"already_done"``).
    """

    cancelled: bool
    reason: str | None = None


# ── Activity feed — S8 (ADR-007 §4 S8) ───────────────────────────────────────


ActivityKind = Literal[
    "session_started",
    "session_ended",
    "tool_call",
    "tool.structured_question",
    "tool.structured_answer",
    "heartbeat_tick",
    "destructive_confirm_requested",
    "destructive_confirm_resolved",
    "telegram_inbound",
    "telegram_outbound",
    "project_archived",
    "project_unarchived",
    "project_paused",
    "project_resumed",
]
"""Closed taxonomy of dashboard activity rows — the ``event_kind``
discriminator on :class:`ActivityRow` (Letta ``message_type`` pattern). A
kind is added here only when a real on-disk/in-memory source emits it; no
speculative entries (no-mock rule)."""


class ActivityRow(_StrictResponse):
    """One row in ``GET /api/activity`` (S8 — ADR-007 §4 S8).

    Source-of-truth: :mod:`selffork_orchestrator.dashboard.activity` merges
    four real sources — session audit JSONL (orphan + per-project), the
    heartbeat audit log, the dashboard activity log (project mutations), and
    the in-memory Telegram activity ring — into one chronological feed. Every
    row derives from an artifact; nothing is fabricated.

    Flat shape with an ``event_kind`` discriminator (Letta ``LettaMessage``
    pattern) rather than 14 subclasses — the feed is heterogeneous-by-row and
    the UI groups visually by ``correlation_id`` (e.g. a
    ``tool.structured_question`` and its ``tool.structured_answer``).
    ``intent`` carries the *why* when the source records it (heartbeat
    reasoning, destructive command summary) — the git-context-controller
    decision-log lift.
    """

    id: str
    ts: datetime
    seq_id: int
    """Epoch-milliseconds of ``ts`` — a sortable ordering value, NOT a unique
    cursor (rows from different sources can share a millisecond). ``?before=
    <iso ts>`` pages to an older window, coarse to the millisecond; the unique,
    stable ``id`` is what clients use to de-duplicate rows across polls."""

    event_kind: ActivityKind
    summary: str
    intent: str | None
    project_slug: str | None
    session_id: str | None
    correlation_id: str | None
    payload: dict[str, object]
    severity: Literal["info", "warn", "error"]


class ActivityResponse(_StrictResponse):
    """Body of ``GET /api/activity`` — rows DESC by ``ts``.

    ``has_more`` is ``True`` when the merge produced more rows than the
    requested ``limit`` (page with ``?before=`` using the last row's ``ts``).
    """

    rows: list[ActivityRow]
    has_more: bool
