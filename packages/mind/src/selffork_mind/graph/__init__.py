"""T3 Semantic Graph backend (ADR-002 §1, §5, §6).

Per ADR-002:

- ``T3 Semantic Graph`` — cross-session facts with causality + temporal
  validity (HippoRAG 2 + Graphiti pattern).
- HippoRAG 2 (ICML 2025, arXiv:2502.14802): passage + phrase nodes
  joined by ``contains`` edges, retrieval via Personalized PageRank.
- Graphiti (arXiv:2501.13956): bi-temporal facts (``valid_from`` /
  ``valid_until`` already on :class:`Note`; the graph layer extends
  this to **triples** between phrase nodes).

This module ships:

- :class:`GraphTriple` — one ``(subject, predicate, object)`` fact, with
  bi-temporal validity.
- :class:`SemanticGraphStore` Protocol — backend-neutral contract.
- :class:`InMemoryGraphStore` — pure-Python reference impl + the test
  backend (no extra deps; deterministic; full HippoRAG 2 PPR support).
- :class:`KuzuGraphStore` — optional embedded Kuzu backend (lazy import,
  ``selffork-mind[graph-kuzu]``); used when the operator wants the same
  data on disk and Cypher-queryable.
- :func:`personalized_pagerank` — pure-Python PPR over passage+phrase.
- :class:`GraphRetriever` — high-level recall over the graph (HippoRAG 2
  routing for multi-hop queries).
- :func:`extract_triples` — deterministic structured-source bypass
  (Cognee pattern): converts Episodic events into 1:1 triples without an
  LLM. LLM-driven triple extraction lands Order 5.
"""

from __future__ import annotations

from selffork_mind.graph.base import (
    GraphTriple,
    PhraseNode,
    SemanticGraphStore,
)
from selffork_mind.graph.consolidation import (
    ConsolidationReport,
    SemanticGraphConsolidator,
    extract_triples,
)
from selffork_mind.graph.in_memory import InMemoryGraphStore
from selffork_mind.graph.kuzu import KuzuGraphStore
from selffork_mind.graph.ppr import personalized_pagerank
from selffork_mind.graph.retriever import GraphHit, GraphRetriever

__all__ = [
    "ConsolidationReport",
    "GraphHit",
    "GraphRetriever",
    "GraphTriple",
    "InMemoryGraphStore",
    "KuzuGraphStore",
    "PhraseNode",
    "SemanticGraphConsolidator",
    "SemanticGraphStore",
    "extract_triples",
    "personalized_pagerank",
]
