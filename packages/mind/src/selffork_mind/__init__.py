"""SelfFork Mind pillar — persistent memory, RAG/GraphRAG, deterministic compaction.

Six-tier cognitive memory architecture per ADR-002:

- **T1 Working** (in-context block) — :mod:`selffork_mind.memory.tiers.working`
- **T2 Episodic** (per-session events, vector) — :mod:`selffork_mind.memory.tiers.episodic`
- **T3 Semantic Graph** (HippoRAG 2 + Graphiti) — :mod:`selffork_mind.memory.tiers.semantic_graph`
- **T4 Procedural** (operator-style reflex patterns) — :mod:`selffork_mind.memory.tiers.procedural`
- **T5 Reflection** (Generative-Agents reflection) — :mod:`selffork_mind.memory.tiers.reflection`
- **T6 Recall** (audit JSONL derivative) — :mod:`selffork_mind.memory.tiers.recall`

Public surface (Order 1):

- :class:`MindStore` — pluggable storage Protocol; reference impl in
  :mod:`selffork_mind.memory.store.duckdb`.
- :class:`EmbeddingProvider` — pluggable embedder Protocol; default impl
  ``BGE-M3`` (multilingual, dense+sparse+ColBERT).
- :class:`Note` / :class:`Tag` / :class:`Filter` — core schema primitives.

Higher orders add T2-T6 implementations, retrievers, compaction, projections,
and the eval suite. Each lands fully production-quality on its order; no MVP
iteration (`feedback_no_mvp_full_quality_first_time`).
"""

from __future__ import annotations

from selffork_mind.bridge import (
    ExportConfig,
    ExportReport,
    ReflexCorpusExporter,
    SM2Card,
    SM2Scheduler,
    TrainingItem,
)
from selffork_mind.compaction import (
    CompactionPlan,
    CompactionStrategy,
    ImportanceDistiller,
    LLMSummaryCompactor,
    MedoidClusterCompactor,
    RecencyDecayCompactor,
    apply_plan,
)
from selffork_mind.graph import (
    GraphRetriever,
    GraphTriple,
    InMemoryGraphStore,
    SemanticGraphConsolidator,
    SemanticGraphStore,
    personalized_pagerank,
)
from selffork_mind.memory.filters import (
    Filter,
    FilterAll,
    FilterAny,
    FilterCondition,
    FilterNot,
    FilterOp,
)
from selffork_mind.memory.model import (
    DataPoint,
    Note,
    NoteKind,
    TierName,
)
from selffork_mind.memory.tags import Tag, TagMatchMode
from selffork_mind.memory.tiers import (
    DistillationReport,
    EpisodicToolCall,
    EpisodicWriter,
    ProceduralDistiller,
    RecallEvent,
    RecallReader,
    RecallSession,
    WorkingBlock,
    WorkingBlockManager,
)
from selffork_mind.rag.retriever import HybridRetriever, classify_query

__all__ = [
    "CompactionPlan",
    "CompactionStrategy",
    "DataPoint",
    "DistillationReport",
    "EpisodicToolCall",
    "EpisodicWriter",
    "ExportConfig",
    "ExportReport",
    "Filter",
    "FilterAll",
    "FilterAny",
    "FilterCondition",
    "FilterNot",
    "FilterOp",
    "GraphRetriever",
    "GraphTriple",
    "HybridRetriever",
    "ImportanceDistiller",
    "InMemoryGraphStore",
    "LLMSummaryCompactor",
    "MedoidClusterCompactor",
    "Note",
    "NoteKind",
    "ProceduralDistiller",
    "RecallEvent",
    "RecallReader",
    "RecallSession",
    "RecencyDecayCompactor",
    "ReflexCorpusExporter",
    "SM2Card",
    "SM2Scheduler",
    "SemanticGraphConsolidator",
    "SemanticGraphStore",
    "Tag",
    "TagMatchMode",
    "TierName",
    "TrainingItem",
    "WorkingBlock",
    "WorkingBlockManager",
    "__version__",
    "apply_plan",
    "classify_query",
    "personalized_pagerank",
]

__version__ = "0.0.1"
