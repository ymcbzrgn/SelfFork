"""SelfFork Mind eval suite — multi-axis vector reporting.

Per ADR-002 §12. Mind quality is reported as a vector across:

- :mod:`selffork_mind.eval.longmemeval` — LongMemEval 5-axis (Wu et al.,
  ICLR 2025): info-extraction, multi-session reasoning, temporal
  reasoning, knowledge-updates, abstention.
- (Order 3+) :mod:`selffork_mind.eval.memoryagentbench` — MemoryAgentBench
  4-axis (Hu, Wang, McAuley, ICLR 2026): Accurate Retrieval, Test-Time
  Learning, Long-Range Understanding, Conflict Resolution.
- (Order 5) :mod:`selffork_mind.eval.perltqa` — episodic + semantic split
  validation (Du et al., SIGHAN-10 2024).
- (Order 6) :mod:`selffork_mind.eval.locomo` — persona + temporal-event-graph
  corpus shape (Maharana et al., ACL 2024).
- (Order 6) :mod:`selffork_mind.eval.operator_holdout` — SelfFork-specific
  held-out corpus (questions authored offline before model sees sessions).

Order 1 ships the LongMemEval dataset loader + scoring harness; downstream
orders fill in the additional axes as their tier landings make those axes
testable.
"""

from __future__ import annotations

from selffork_mind.eval.longmemeval import (
    LongMemEvalAxis,
    LongMemEvalQuestion,
    LongMemEvalReport,
    LongMemEvalScorer,
    load_longmemeval_dataset,
)

__all__ = [
    "LongMemEvalAxis",
    "LongMemEvalQuestion",
    "LongMemEvalReport",
    "LongMemEvalScorer",
    "load_longmemeval_dataset",
]
