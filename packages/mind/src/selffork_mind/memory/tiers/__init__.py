"""Six-tier cognitive memory implementations (per ADR-002 §1).

- :mod:`.recall` — T6 Recall (audit JSONL read tier). **Order 1 landed.**
- ``episodic`` — T2 Episodic per-round writer. **Order 2 in progress.**
- ``working`` — T1 Working in-context block. *Order 3.*
- ``procedural`` — T4 Procedural reflex patterns. *Order 3.*
- ``semantic_graph`` — T3 graph store. *Order 4.*
- ``reflection`` — T5 generative-agents reflection. *Order 5.*

Each tier is a separate module so its dependencies (e.g. Kuzu graph for
T3) can stay opt-in. The ``MindStore`` Protocol underlies T1-T5; T6 reads
from filesystem-only audit JSONL and uses no store.
"""

from __future__ import annotations

from selffork_mind.memory.tiers.episodic import (
    EpisodicToolCall,
    EpisodicWriter,
    detect_sentinels,
)
from selffork_mind.memory.tiers.procedural import (
    DistillationReport,
    ProceduralDistiller,
)
from selffork_mind.memory.tiers.recall import (
    RecallEvent,
    RecallReader,
    RecallSession,
)
from selffork_mind.memory.tiers.reflection import (
    ReflectionReport,
    Reflector,
)
from selffork_mind.memory.tiers.working import (
    WorkingBlock,
    WorkingBlockManager,
)

__all__ = [
    "DistillationReport",
    "EpisodicToolCall",
    "EpisodicWriter",
    "ProceduralDistiller",
    "RecallEvent",
    "RecallReader",
    "RecallSession",
    "ReflectionReport",
    "Reflector",
    "WorkingBlock",
    "WorkingBlockManager",
    "detect_sentinels",
]
