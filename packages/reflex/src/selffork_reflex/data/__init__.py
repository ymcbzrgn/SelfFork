"""Reflex data pipeline -- session-capture normalizer + corpus assembly.

S-Train (ADR-012) builds the fine-tune corpus on the frozen wire contracts,
per ``docs/Operator_Locked_Decisions.md``. Landed here:

  - T1 session-capture normalizer (``normalize.py``): SelfFork's own session
    audit JSONL -> locked session-aware chat samples with the Yamac-only
    weighted-loss mask (0.0 agent/tool/context, 0.3 prior operator, 1.0 target).

Still to land (skeleton until their S-Train items):
  - External export readers (Claude Code JSONL, OpenCode / ChatGPT export)
  - T2 corpus assembler (multi-session, source precedence)
  - T5 corpus validator
"""

from __future__ import annotations

from selffork_reflex.data.normalize import (
    INACTIVE_WEIGHT,
    OPERATOR_CATEGORIES,
    PRIOR_OPERATOR_WEIGHT,
    SYSTEM_PROMPT,
    TARGET_OPERATOR_WEIGHT,
    AuditEventLike,
    ChatMessage,
    MessageRole,
    SessionEvent,
    TrainingSample,
    event_to_message,
    normalize_from_audit,
    normalize_session,
    session_event_from_mapping,
    session_events_from_audit,
)

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
