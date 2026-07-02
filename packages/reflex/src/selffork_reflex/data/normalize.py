"""Session-capture normalizer -- SelfFork's own audit JSONL to training samples.

Turns one SelfFork session's ordered audit events into the locked
"session-aware chat" training sample format (see
``docs/Operator_Locked_Decisions.md`` sections 2 + 3, and
``docs/decisions/ADR-012_S-Train_Corpus.md`` section 2). This is S-Train item
T1: corpus assembly on the frozen wire contracts, with NO GPU / training work.

Input source (T1 scope)
------------------------
SelfFork's OWN session audit log, one file per session at
``<audit_dir>/<session_id>.jsonl`` -- exactly what
``selffork_shared.audit.AuditLogger`` writes and
``selffork_shared.audit_reader`` parses into ``RawAuditEvent`` records
(fields: ``category``, ``payload``, plus ts/level/event/session_id).

Follow-up (NOT this item): external transcript readers -- Claude Code session
JSONL, OpenCode export, ChatGPT export, Claude.ai ARGE history
(``Operator_Locked_Decisions.md`` section 4 "Primary/Secondary" sources). Those
carry full assistant text SelfFork's own audit does not store (agent.output
keeps only char counts, not the CLI transcript); a later S-Train item adds those
readers. This module deliberately does not build them.

Operator-vs-agent discriminator
-------------------------------
In SelfFork's own autonomous round loop
(``selffork_orchestrator.lifecycle.session.Session._run_agent``) the LOCAL model
plays the operator (Yamac) role: it emits the next driving message, the CLI
agent (Claude Code / OpenCode) executes it, tools run, and the loop repeats. The
audit category that carries that operator-role message is ``selffork_jr.reply``
-- the source variable is literally named ``yamac_reply`` and the text lives in
``payload["text"]``. So within this audit stream the operator (Yamac) message
discriminator is ``category == "selffork_jr.reply"`` (see
:data:`OPERATOR_CATEGORIES`). Everything else -- ``agent.*`` (the driven CLI
agent), ``tool.*`` (tool calls/results), and lifecycle categories
(session/runtime/sandbox/plan/loop/mind/body/provider/...) -- is non-operator
context and carries loss weight 0.0.

Loss mask (``Operator_Locked_Decisions.md`` section 3, Yamac-only weighted loss)
-------------------------------------------------------------------------------
- agent / assistant / tool / context messages -> 0.0
- previous operator (Yamac) messages in the prefix -> 0.3
- the final target operator (Yamac) message -> 1.0

Purity
------
:func:`normalize_session` is a pure function over already-parsed
:class:`SessionEvent` records, so ``selffork-reflex`` stays dependency-free
(no ``selffork-shared`` import, safe on the locked-resolution dev box). The thin
``audit_reader`` glue -- :func:`session_events_from_audit` /
:func:`normalize_from_audit` -- is structural (a :class:`AuditEventLike`
Protocol), so a caller that already has ``selffork-shared`` can feed
``RawAuditEvent`` objects straight through without this package depending on it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

__all__ = [
    "INACTIVE_WEIGHT",
    "OPERATOR_CATEGORIES",
    "PRIOR_OPERATOR_WEIGHT",
    "SYSTEM_PROMPT",
    "TARGET_OPERATOR_WEIGHT",
    "AuditEventLike",
    "ChatMessage",
    "MessageRole",
    "SessionEvent",
    "TrainingSample",
    "event_to_message",
    "normalize_from_audit",
    "normalize_session",
    "session_event_from_mapping",
    "session_events_from_audit",
]

# Canonical system prompt -- verbatim from docs/Operator_Locked_Decisions.md
# section 2. Frozen input: changing it is a retraining event (ADR-012 section 3).
# The Turkish name keeps its cedilla here on purpose (allowed-confusables in
# the repo ruff config); this is corpus data, not a comment.
SYSTEM_PROMPT = (
    "You are Yamaç Jr. Nano. Your task is to predict how Yamaç would respond "
    "in this situation."
)

# Loss weights (Operator_Locked_Decisions.md section 3).
TARGET_OPERATOR_WEIGHT = 1.0
PRIOR_OPERATOR_WEIGHT = 0.3
INACTIVE_WEIGHT = 0.0

# Audit categories that represent an operator (Yamac) message in SelfFork's own
# session audit. Kept as a set so the discriminator is explicit and extensible
# (e.g. a future external-reader item may add its operator-turn category) rather
# than hard-coded at the comparison site.
OPERATOR_CATEGORIES: frozenset[str] = frozenset({"selffork_jr.reply"})

# Role of a chat message in a session-aware sample. Maps onto the loss table:
#   system     -> framing, weight 0.0
#   operator   -> Yamac (weight 0.3 in prefix, 1.0 as target)
#   assistant  -> the driven CLI agent (Claude Code / OpenCode), weight 0.0
#   tool       -> tool call / result, weight 0.0
#   context    -> session lifecycle / repo context, weight 0.0
MessageRole = Literal["system", "operator", "assistant", "tool", "context"]

# Payload keys, in priority order, that carry human/agent-readable text. The
# operator message text lives under "text"; the rest give non-operator (weight
# 0.0) messages some faithful content without a per-category switch.
_TEXT_KEYS: tuple[str, ...] = (
    "text",
    "result_payload_preview",
    "output",
    "message",
    "detail",
    "reason",
)


@dataclass(frozen=True, slots=True)
class SessionEvent:
    """One parsed audit event fed to the pure normalizer.

    Mirrors the two ``selffork_shared.audit_reader.RawAuditEvent`` fields that
    drive normalization (``category`` + ``payload``). Defined locally so the
    pure core is testable with plain synthetic data and this package needs no
    runtime dependency.
    """

    category: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One role-tagged message in a session-aware chat sample.

    ``loss_weight`` is the per-message training weight (see the module loss
    table): 0.0 for system/agent/tool/context, 0.3 for a prior operator
    message, 1.0 for the target operator message.
    """

    role: MessageRole
    content: str
    loss_weight: float


@dataclass(frozen=True, slots=True)
class TrainingSample:
    """One session-aware training sample.

    ``messages`` is ``[system, *session_prefix, target]`` in session order;
    ``target_index`` points at the final (target) operator message, which is
    always ``len(messages) - 1``.
    """

    session_id: str
    messages: list[ChatMessage]
    target_index: int


class AuditEventLike(Protocol):
    """Structural type for a parsed audit event.

    Read-only ``category`` + ``payload`` -- matches
    ``selffork_shared.audit_reader.RawAuditEvent`` (a frozen dataclass whose
    ``payload`` is a ``dict``) without importing it, so this package stays
    dependency-free while callers that already have ``selffork-shared`` can pass
    ``RawAuditEvent`` values straight into the glue helpers.
    """

    @property
    def category(self) -> str: ...

    @property
    def payload(self) -> Mapping[str, object]: ...


def _role_for(category: str) -> MessageRole:
    """Map an audit category to its chat role (see :data:`MessageRole`)."""
    if category in OPERATOR_CATEGORIES:
        return "operator"
    if category.startswith("agent."):
        return "assistant"
    if category.startswith("tool."):
        return "tool"
    return "context"


def _content_for(category: str, payload: Mapping[str, object]) -> str:
    """Extract faithful, deterministic message content from an event payload.

    Operator text (``payload["text"]``) is the load-bearing content; for
    non-operator events we surface the best available text field, then a
    tool-name/args rendering, then the category itself as a stable fallback so
    content is never empty.
    """
    for key in _TEXT_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    tool = payload.get("tool")
    if isinstance(tool, str) and tool:
        args = payload.get("args")
        status = payload.get("status")
        if args is not None:
            return f"{tool} {args}"
        if isinstance(status, str) and status:
            return f"{tool} -> {status}"
        return tool
    return category


def event_to_message(event: SessionEvent) -> ChatMessage:
    """Map one event to a chat message with its BASE (non-target) loss weight.

    Operator messages get :data:`PRIOR_OPERATOR_WEIGHT`; everything else gets
    :data:`INACTIVE_WEIGHT`. :func:`normalize_session` re-stamps the single
    target operator message to :data:`TARGET_OPERATOR_WEIGHT`.
    """
    role = _role_for(event.category)
    weight = PRIOR_OPERATOR_WEIGHT if role == "operator" else INACTIVE_WEIGHT
    return ChatMessage(
        role=role,
        content=_content_for(event.category, event.payload),
        loss_weight=weight,
    )


def normalize_session(
    events: Sequence[SessionEvent],
    *,
    session_id: str = "",
    system_prompt: str = SYSTEM_PROMPT,
) -> list[TrainingSample]:
    """Emit one training sample per operator (Yamac) message in ``events``.

    Pure function. For each operator message the sample is
    ``[system, *full_session_prefix_up_to_and_including_that_message]`` where
    the prefix keeps its base weights (prior operator messages 0.3, all else
    0.0) and the final message -- the target operator message -- is re-stamped
    to weight 1.0. Sessions with zero operator messages yield zero samples.

    ``session_id`` is copied onto every emitted sample (the pure core does not
    read it from the events); the glue helpers pass it through.
    """
    system_message = ChatMessage(
        role="system",
        content=system_prompt,
        loss_weight=INACTIVE_WEIGHT,
    )
    base_messages = [event_to_message(event) for event in events]

    samples: list[TrainingSample] = []
    for index, message in enumerate(base_messages):
        if message.role != "operator":
            continue
        # Prefix = every message before this one, with base weights already
        # applied (prior operator messages sit at PRIOR_OPERATOR_WEIGHT).
        prefix = base_messages[:index]
        target = ChatMessage(
            role="operator",
            content=message.content,
            loss_weight=TARGET_OPERATOR_WEIGHT,
        )
        sample_messages = [system_message, *prefix, target]
        samples.append(
            TrainingSample(
                session_id=session_id,
                messages=sample_messages,
                target_index=len(sample_messages) - 1,
            )
        )
    return samples


def session_event_from_mapping(obj: Mapping[str, object]) -> SessionEvent:
    """Adapt a raw parsed JSONL object (``{category, payload, ...}``) to a
    :class:`SessionEvent`. Missing/loose fields degrade to empty values.
    """
    payload = obj.get("payload")
    return SessionEvent(
        category=str(obj.get("category", "")),
        payload=payload if isinstance(payload, Mapping) else {},
    )


def session_events_from_audit(events: Iterable[AuditEventLike]) -> list[SessionEvent]:
    """Thin ``audit_reader`` glue: adapt parsed audit events (e.g.
    ``selffork_shared.audit_reader.RawAuditEvent``) to :class:`SessionEvent`.

    Structural over :class:`AuditEventLike`, so this stays dependency-free.
    """
    return [SessionEvent(category=event.category, payload=event.payload) for event in events]


def normalize_from_audit(
    events: Iterable[AuditEventLike],
    *,
    session_id: str = "",
    system_prompt: str = SYSTEM_PROMPT,
) -> list[TrainingSample]:
    """Convenience: adapt parsed audit events then :func:`normalize_session`.

    Intended for callers that already hold ``selffork-shared`` and can read one
    session file via ``selffork_shared.audit_reader.iter_session_events``. The
    external Claude Code / OpenCode / ChatGPT export readers are a later S-Train
    item and are intentionally out of scope here.
    """
    parsed = session_events_from_audit(events)
    return normalize_session(parsed, session_id=session_id, system_prompt=system_prompt)
