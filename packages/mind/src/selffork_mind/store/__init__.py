"""Pluggable storage backends for SelfFork Mind.

Per ADR-002 §2: DuckDB (relational + filter DSL) + LanceDB (vectors +
time-travel) + Kuzu (graph). Order 1 shipped DuckDB; S-Memory adds LanceDB
(T2 Episodic vectors) + Pool resolver (dual-pool ADR-009).

Public surface:

- :class:`MindStore` — Protocol; the contract every backend implements.
- :class:`DuckDBMindStore` — relational + filter DSL + vector cosine fallback.
- :class:`LanceDBVectorStore` — high-scale vector store for T2 Episodic.
- :class:`PoolResolver` — dual-pool routing (PROJECT + GLOBAL), ADR-009.
- :class:`PoolScope` / :class:`StoreScope` — typed scope.
- :class:`RetrieveConfig` / :class:`RetrievalHit` — typed query / result.
"""

from __future__ import annotations

from selffork_mind.store.base import (
    GLOBAL_GROUP_ID,
    MindStore,
    PoolScope,
    RetrievalHit,
    RetrieveConfig,
    StoreScope,
    TierStats,
    derive_group_id,
    project_group_id,
)
from selffork_mind.store.duckdb import DuckDBMindStore
from selffork_mind.store.lance import LanceDBVectorStore
from selffork_mind.store.pool import (
    PoolPaths,
    PoolResolver,
    default_global_pool_root,
    default_project_pool_root,
)

__all__ = [
    "GLOBAL_GROUP_ID",
    "DuckDBMindStore",
    "LanceDBVectorStore",
    "MindStore",
    "PoolPaths",
    "PoolResolver",
    "PoolScope",
    "RetrievalHit",
    "RetrieveConfig",
    "StoreScope",
    "TierStats",
    "default_global_pool_root",
    "default_project_pool_root",
    "derive_group_id",
    "project_group_id",
]
