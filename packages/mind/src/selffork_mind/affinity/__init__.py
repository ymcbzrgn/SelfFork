"""CLI affinity store — ADR-006 §4.6 RAG performance layer (S6).

Records ``(task_type, cli) → success`` outcomes per ADR-009 dual pool
(PROJECT codebase affinity + GLOBAL operator reflex) and scores CLI
candidates with a frequentist, Laplace-smoothed, recency-decayed,
hierarchically-pooled success rate. The orchestrator CLI router
(ADR-006 §4.6) takes the deterministic argmax over these scores.

Public surface:

- :class:`CliAffinityResolver` — dual-pool record + score coordinator.
- :func:`build_duckdb_affinity_resolver` — file-backed factory.
- :class:`CliAffinityStore` — single-pool backend Protocol.
- :class:`InMemoryCliAffinityStore` / :class:`DuckDBCliAffinityStore`.
- :class:`AffinityConfig` / :class:`AffinityRecord` / :class:`AffinityScore`.
"""

from __future__ import annotations

from selffork_mind.affinity.model import (
    AffinityConfig,
    AffinityRecord,
    AffinityScore,
    MatchLevel,
    laplace_rate,
    shrink,
)
from selffork_mind.affinity.resolver import (
    CliAffinityResolver,
    build_duckdb_affinity_resolver,
    global_affinity_db_path,
    project_affinity_db_path,
)
from selffork_mind.affinity.store import (
    CliAffinityStore,
    DuckDBCliAffinityStore,
    InMemoryCliAffinityStore,
)

__all__ = [
    "AffinityConfig",
    "AffinityRecord",
    "AffinityScore",
    "CliAffinityResolver",
    "CliAffinityStore",
    "DuckDBCliAffinityStore",
    "InMemoryCliAffinityStore",
    "MatchLevel",
    "build_duckdb_affinity_resolver",
    "global_affinity_db_path",
    "laplace_rate",
    "project_affinity_db_path",
    "shrink",
]
