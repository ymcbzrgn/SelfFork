"""SelfFork tool-mastery synthetic corpus (S-Train, teacher = Claude).

The base model can auto tool-call in general but fails on SelfFork's SPECIFIC
289-tool surface (~20% success). This package builds the synthetic training
corpus that teaches a tiny fine-tuned model to emit the exact
``<selffork-tool-call>`` blocks + the 10 closed LegalActions correctly (target
90%+), on SelfFork's own tools only.

Correctness is guaranteed by construction: every authored example is run
through :mod:`selffork_orchestrator.corpus.validator`, which validates each
tool call against the REAL registry (``args_model.model_validate`` -- the exact
check the runtime runs). A target that would not round-trip is rejected before
it can poison the corpus. The reflex ``data`` package owns the pure corpus
schema / loss-mask; this package owns the tool-aware generation + validation
(it needs the tool registry, which lives in the orchestrator).
"""

from __future__ import annotations

from selffork_orchestrator.corpus.validator import (
    LEGAL_ACTION_LABELS,
    ReplyValidation,
    ToolCallCheck,
    default_registry,
    validate_legal_action,
    validate_reply,
    validate_tool_call,
)

__all__ = [
    "LEGAL_ACTION_LABELS",
    "ReplyValidation",
    "ToolCallCheck",
    "default_registry",
    "validate_legal_action",
    "validate_reply",
    "validate_tool_call",
]
