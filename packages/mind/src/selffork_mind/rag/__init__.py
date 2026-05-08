"""Retrieval-augmented generation primitives for SelfFork Mind.

Per ADR-002 §3-§5. Pluggable embedders + rerankers; retriever lands in
Order 2 (T2 Episodic).

Public surface:

- :class:`EmbeddingProvider` Protocol + 6 implementations (BGE-M3 default).
- :class:`RerankerProvider` Protocol + 4 implementations (BGE-rerank default).
- :func:`build_embedder` / :func:`build_reranker` — name-based factory.
"""

from __future__ import annotations

from selffork_mind.rag.embedder import (
    BGEM3Embedder,
    EmbedderName,
    EmbeddingProvider,
    GeminiEmbedder,
    GemmaEmbedder,
    JinaEmbedder,
    OllamaEmbedder,
    OpenAIEmbedder,
    build_embedder,
)
from selffork_mind.rag.reranker import (
    BGERerankerV2M3,
    CohereReranker,
    JinaReranker,
    RerankerName,
    RerankerProvider,
    VoyageReranker,
    build_reranker,
)
from selffork_mind.rag.retriever import (
    HybridRetriever,
    QueryRoute,
    classify_query,
)
from selffork_mind.rag.scoring import (
    BM25Scorer,
    ConvexFusionScorer,
    ScoredCandidate,
    Scorer,
    SemanticScorer,
    TagBoostScorer,
    tokenize,
)

__all__ = [
    "BGEM3Embedder",
    "BGERerankerV2M3",
    "BM25Scorer",
    "CohereReranker",
    "ConvexFusionScorer",
    "EmbedderName",
    "EmbeddingProvider",
    "GeminiEmbedder",
    "GemmaEmbedder",
    "HybridRetriever",
    "JinaEmbedder",
    "JinaReranker",
    "OllamaEmbedder",
    "OpenAIEmbedder",
    "QueryRoute",
    "RerankerName",
    "RerankerProvider",
    "ScoredCandidate",
    "Scorer",
    "SemanticScorer",
    "TagBoostScorer",
    "VoyageReranker",
    "build_embedder",
    "build_reranker",
    "classify_query",
    "tokenize",
]
