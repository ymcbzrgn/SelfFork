"""Reflex data pipeline -- session-capture normalizer + corpus assembly.

S-Train (ADR-012) builds the fine-tune corpus on the frozen wire contracts,
per ``docs/Operator_Locked_Decisions.md``. Landed here:

  - T1 session-capture normalizer (``normalize.py``): SelfFork's own session
    audit JSONL -> locked session-aware chat samples with the Yamac-only
    weighted-loss mask (0.0 agent/tool/context, 0.3 prior operator, 1.0 target).
  - T2 corpus assembler (``assemble.py``): multi-session -> one flat corpus,
    source-precedence ordered (Operator_Locked_Decisions section 4), serialized
    to the corpus JSONL artifact.
  - T5 corpus validator (``validate.py``): schema + loss-mask integrity + source
    attribution + agentic-trace-length distribution (ADR-010 section 2.3).

Still to land (skeleton until their S-Train items):
  - External export readers (Claude Code JSONL, OpenCode / ChatGPT export)
"""

from __future__ import annotations

from selffork_reflex.data.assemble import (
    SOURCE_PRECEDENCE,
    CorpusSample,
    SessionCapture,
    assemble_corpus,
    corpus_to_jsonl,
    sample_to_dict,
    source_rank,
    write_corpus,
)
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
from selffork_reflex.data.validate import (
    AGENTIC_TRACE_TOOL_TARGET,
    KNOWN_SOURCES,
    VALID_ROLES,
    ValidationReport,
    validate_corpus_file,
    validate_corpus_rows,
)

__all__ = [
    "AGENTIC_TRACE_TOOL_TARGET",
    "INACTIVE_WEIGHT",
    "KNOWN_SOURCES",
    "OPERATOR_CATEGORIES",
    "PRIOR_OPERATOR_WEIGHT",
    "SOURCE_PRECEDENCE",
    "SYSTEM_PROMPT",
    "TARGET_OPERATOR_WEIGHT",
    "VALID_ROLES",
    "AuditEventLike",
    "ChatMessage",
    "CorpusSample",
    "MessageRole",
    "SessionCapture",
    "SessionEvent",
    "TrainingSample",
    "ValidationReport",
    "assemble_corpus",
    "corpus_to_jsonl",
    "event_to_message",
    "normalize_from_audit",
    "normalize_session",
    "sample_to_dict",
    "session_event_from_mapping",
    "session_events_from_audit",
    "source_rank",
    "validate_corpus_file",
    "validate_corpus_rows",
    "write_corpus",
]
