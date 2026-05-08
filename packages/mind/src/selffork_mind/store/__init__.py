"""Pluggable storage backends for SelfFork Mind.

Per ADR-002 §2: DuckDB (relational + filter DSL) + LanceDB (vectors +
time-travel) + Kuzu (graph). Order 1 ships DuckDB only; LanceDB lands in
Order 2 (T2 Episodic vectors) and Kuzu in Order 4 (T3 Semantic Graph).

Public surface:

- :class:`MindStore` — Protocol; the contract every backend implements.
- :class:`DuckDBMindStore` — reference implementation used by all tiers.
- :class:`RetrieveConfig` / :class:`RetrievalHit` — typed query / result.
"""

from __future__ import annotations

from selffork_mind.store.base import (
    MindStore,
    RetrievalHit,
    RetrieveConfig,
    StoreScope,
)
from selffork_mind.store.duckdb import DuckDBMindStore

__all__ = [
    "DuckDBMindStore",
    "MindStore",
    "RetrievalHit",
    "RetrieveConfig",
    "StoreScope",
]
