"""RerankerProvider Protocol + four implementations.

Per ADR-002 §3b. Pluggable cross-encoder rerank stage that sits between
vector/graph candidate retrieval and final selection. Rerank dramatically
improves precision on multi-hop / temporal / domain-specific queries — the
embedding stage runs cheap and recall-broad, the rerank stage runs
expensive and precision-narrow.

Implementations:

- :class:`BGERerankerV2M3` — local sentence-transformers (default).
- :class:`JinaReranker` — Jina AI ``rerank-v2-base-multilingual``.
- :class:`CohereReranker` — Cohere ``rerank-multilingual-v3.0``.
- :class:`VoyageReranker` — Voyage AI ``rerank-2``.

All implementations expose the same async surface returning a relevance
score per candidate. The caller sorts and slices.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Literal

import httpx

__all__ = [
    "BGERerankerV2M3",
    "CohereReranker",
    "JinaReranker",
    "RerankerName",
    "RerankerProvider",
    "VoyageReranker",
    "build_reranker",
]


RerankerName = Literal[
    "bge-rerank-v2-m3",
    "jina",
    "cohere",
    "voyage",
]


class RerankerProvider(ABC):
    """Abstract base for cross-encoder rerank backends."""

    @property
    @abstractmethod
    def name(self) -> RerankerName:
        """Stable string id used by config and audit log."""

    @property
    def supports_multilingual(self) -> bool:
        """True if the backend is trained on multilingual data."""
        return False

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: Sequence[str],
    ) -> list[float]:
        """Return a relevance score per candidate (same order as input).

        Higher score = more relevant. Caller sorts and slices to ``top_k``.
        """


# ── BGE-reranker-v2-m3 (default) ────────────────────────────────────────────


class BGERerankerV2M3(RerankerProvider):
    """Local sentence-transformers ``BAAI/bge-reranker-v2-m3``.

    Multilingual cross-encoder; 100+ languages including Turkish.

    Install: ``pip install 'selffork-mind[rerankers-bge]'``.
    """

    _MODEL_ID: str = "BAAI/bge-reranker-v2-m3"

    def __init__(self, *, model_id: str | None = None) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - optional dep error path
            raise ImportError(
                "BGE reranker requires sentence-transformers. "
                "Install: pip install 'selffork-mind[rerankers-bge]'",
            ) from exc
        self._model = CrossEncoder(model_id or self._MODEL_ID)

    @property
    def name(self) -> RerankerName:
        return "bge-rerank-v2-m3"

    @property
    def supports_multilingual(self) -> bool:
        return True

    async def rerank(
        self,
        query: str,
        candidates: Sequence[str],
    ) -> list[float]:
        if not candidates:
            return []
        pairs = [(query, c) for c in candidates]
        scores = self._model.predict(
            pairs,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [float(s) for s in scores]


# ── Jina ────────────────────────────────────────────────────────────────────


class JinaReranker(RerankerProvider):
    """Jina AI ``rerank-v2-base-multilingual``.

    API key from ``JINA_API_KEY`` env var. Uses httpx (core dep).
    """

    _ENDPOINT: str = "https://api.jina.ai/v1/rerank"
    _MODEL_ID: str = "jina-reranker-v2-base-multilingual"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        key = api_key or os.environ.get("JINA_API_KEY")
        if not key:
            raise ValueError(
                "Jina reranker needs an API key. Set JINA_API_KEY env var or pass api_key=...",
            )
        self._key = key
        self._model = model or self._MODEL_ID
        self._timeout = timeout_seconds

    @property
    def name(self) -> RerankerName:
        return "jina"

    @property
    def supports_multilingual(self) -> bool:
        return True

    async def rerank(
        self,
        query: str,
        candidates: Sequence[str],
    ) -> list[float]:
        if not candidates:
            return []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "query": query,
                    "documents": list(candidates),
                    "return_documents": False,
                    "top_n": len(candidates),
                },
            )
            response.raise_for_status()
            data = response.json()
        # API returns ``results`` sorted by score; we need scores in the
        # original candidate order, so reindex.
        scores = [0.0] * len(candidates)
        for entry in data["results"]:
            scores[entry["index"]] = float(entry["relevance_score"])
        return scores


# ── Cohere ──────────────────────────────────────────────────────────────────


class CohereReranker(RerankerProvider):
    """Cohere ``rerank-multilingual-v3.0``.

    API key from ``COHERE_API_KEY`` env var.
    Install: ``pip install 'selffork-mind[rerankers-cohere]'``.
    """

    _MODEL_ID: str = "rerank-multilingual-v3.0"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        try:
            import cohere
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Cohere reranker requires cohere. "
                "Install: pip install 'selffork-mind[rerankers-cohere]'",
            ) from exc
        key = api_key or os.environ.get("COHERE_API_KEY")
        if not key:
            raise ValueError(
                "Cohere reranker needs an API key. Set COHERE_API_KEY env var or pass api_key=...",
            )
        self._client = cohere.AsyncClientV2(api_key=key)
        self._model = model or self._MODEL_ID

    @property
    def name(self) -> RerankerName:
        return "cohere"

    @property
    def supports_multilingual(self) -> bool:
        return True

    async def rerank(
        self,
        query: str,
        candidates: Sequence[str],
    ) -> list[float]:
        if not candidates:
            return []
        response = await self._client.rerank(
            model=self._model,
            query=query,
            documents=list(candidates),
            top_n=len(candidates),
        )
        scores = [0.0] * len(candidates)
        for entry in response.results:
            scores[entry.index] = float(entry.relevance_score)
        return scores


# ── Voyage ──────────────────────────────────────────────────────────────────


class VoyageReranker(RerankerProvider):
    """Voyage AI ``rerank-2``.

    API key from ``VOYAGE_API_KEY`` env var.
    Install: ``pip install 'selffork-mind[rerankers-voyage]'``.
    """

    _MODEL_ID: str = "rerank-2"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        try:
            import voyageai
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Voyage reranker requires voyageai. "
                "Install: pip install 'selffork-mind[rerankers-voyage]'",
            ) from exc
        key = api_key or os.environ.get("VOYAGE_API_KEY")
        if not key:
            raise ValueError(
                "Voyage reranker needs an API key. Set VOYAGE_API_KEY env var or pass api_key=...",
            )
        self._client = voyageai.AsyncClient(api_key=key)
        self._model = model or self._MODEL_ID

    @property
    def name(self) -> RerankerName:
        return "voyage"

    async def rerank(
        self,
        query: str,
        candidates: Sequence[str],
    ) -> list[float]:
        if not candidates:
            return []
        response = await self._client.rerank(
            query=query,
            documents=list(candidates),
            model=self._model,
            top_k=len(candidates),
        )
        scores = [0.0] * len(candidates)
        for entry in response.results:
            scores[entry.index] = float(entry.relevance_score)
        return scores


# ── Factory ─────────────────────────────────────────────────────────────────


def build_reranker(name: RerankerName, **kwargs: object) -> RerankerProvider:
    """Look up a reranker class by name and construct it."""
    table: dict[RerankerName, type[RerankerProvider]] = {
        "bge-rerank-v2-m3": BGERerankerV2M3,
        "jina": JinaReranker,
        "cohere": CohereReranker,
        "voyage": VoyageReranker,
    }
    cls = table.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown reranker {name!r}; expected one of {sorted(table)}",
        )
    return cls(**kwargs)
