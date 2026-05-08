"""EmbeddingProvider Protocol + six implementations.

Per ADR-002 §3. Pluggable interface, BGE-M3 default.

Each implementation is a separate class so the optional dependency for
that backend is loaded only when the user constructs that class. The
factory :func:`build_embedder` looks up by name from settings.

Implementations:

- :class:`BGEM3Embedder` — local sentence-transformers (default).
- :class:`OpenAIEmbedder` — OpenAI ``text-embedding-3-{small,large}``.
- :class:`GeminiEmbedder` — Google AI Studio ``text-embedding-004``.
- :class:`JinaEmbedder` — Jina AI ``embeddings-v3``.
- :class:`OllamaEmbedder` — local Ollama HTTP API.
- :class:`GemmaEmbedder` — SelfFork's Reflex mlx-server hidden-state pooling
  (experimental; quality not validated for Q4_0).

All implementations expose the same async surface so callers never branch on
backend identity.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar, Literal

import httpx
import numpy as np

__all__ = [
    "BGEM3Embedder",
    "EmbedderName",
    "EmbeddingProvider",
    "GeminiEmbedder",
    "GemmaEmbedder",
    "JinaEmbedder",
    "OllamaEmbedder",
    "OpenAIEmbedder",
    "build_embedder",
]


EmbedderName = Literal[
    "bge-m3",
    "openai",
    "gemini",
    "jina",
    "ollama",
    "gemma",
]


class EmbeddingProvider(ABC):
    """Abstract base for embedding backends.

    Subclasses must implement :meth:`embed`. :meth:`embed_query` defaults to
    a single-text call through :meth:`embed`; backends with a query-specific
    encoder (e.g. Jina ``retrieval.query`` task) override it.
    """

    @property
    @abstractmethod
    def name(self) -> EmbedderName:
        """Stable string id used by config and audit log."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Output vector dimension. Used to pre-allocate storage."""

    @property
    def supports_multilingual(self) -> bool:
        """True if the backend is trained on multilingual data (English + Turkish + …)."""
        return False

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of documents. Returns a list of float vectors."""

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string. Default: ``embed([text])[0]``."""
        result = await self.embed([text])
        return result[0]


# ── BGE-M3 (default) ────────────────────────────────────────────────────────


class BGEM3Embedder(EmbeddingProvider):
    """Local sentence-transformers BGE-M3.

    BGE-M3 is multilingual (100+ languages incl. Turkish), 1024-dim, and a
    single model produces dense + sparse + ColBERT outputs. We use the dense
    output here; sparse + ColBERT can be wired into the retriever later.

    Install: ``pip install 'selffork-mind[embedders-bge]'``.
    """

    _MODEL_ID: str = "BAAI/bge-m3"
    _DIMENSION: int = 1024

    def __init__(self, *, model_id: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - optional dep error path
            raise ImportError(
                "BGE-M3 embedder requires sentence-transformers. "
                "Install: pip install 'selffork-mind[embedders-bge]'",
            ) from exc
        self._model = SentenceTransformer(model_id or self._MODEL_ID)

    @property
    def name(self) -> EmbedderName:
        return "bge-m3"

    @property
    def dimension(self) -> int:
        return self._DIMENSION

    @property
    def supports_multilingual(self) -> bool:
        return True

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        # sentence-transformers is sync; we accept the synchronous call inside
        # an async method because typical batch sizes (≤128) finish in <1s and
        # the orchestrator runs Mind operations on a worker thread anyway.
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [list(map(float, np.asarray(v))) for v in vectors]


# ── OpenAI ──────────────────────────────────────────────────────────────────


class OpenAIEmbedder(EmbeddingProvider):
    """OpenAI ``text-embedding-3-small`` (default) / ``-large``.

    API key from ``OPENAI_API_KEY`` env var.
    Install: ``pip install 'selffork-mind[embedders-openai]'``.
    """

    _DIMS: ClassVar[dict[str, int]] = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
    }

    def __init__(
        self,
        *,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
    ) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "OpenAI embedder requires openai. "
                "Install: pip install 'selffork-mind[embedders-openai]'",
            ) from exc
        if model not in self._DIMS:
            raise ValueError(
                f"Unknown OpenAI embedding model {model!r}; expected one of {sorted(self._DIMS)}",
            )
        self._client = AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self._model = model

    @property
    def name(self) -> EmbedderName:
        return "openai"

    @property
    def dimension(self) -> int:
        return self._DIMS[self._model]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=list(texts),
        )
        return [list(d.embedding) for d in response.data]


# ── Gemini ──────────────────────────────────────────────────────────────────


class GeminiEmbedder(EmbeddingProvider):
    """Google AI Studio ``text-embedding-004``.

    Multilingual, 768-dim. API key from ``GEMINI_API_KEY`` (or
    ``GOOGLE_API_KEY``) env var.

    Install: ``pip install 'selffork-mind[embedders-gemini]'``.
    """

    _DIMENSION: int = 768
    _MODEL_ID: str = "models/text-embedding-004"

    def __init__(self, *, api_key: str | None = None) -> None:
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Gemini embedder requires google-generativeai. "
                "Install: pip install 'selffork-mind[embedders-gemini]'",
            ) from exc
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ValueError(
                "Gemini embedder needs an API key. Set GEMINI_API_KEY env var or pass api_key=...",
            )
        genai.configure(api_key=key)
        self._genai = genai

    @property
    def name(self) -> EmbedderName:
        return "gemini"

    @property
    def dimension(self) -> int:
        return self._DIMENSION

    @property
    def supports_multilingual(self) -> bool:
        return True

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        # google-generativeai's embed_content is sync; the orchestrator runs
        # Mind ops on a worker thread, so blocking inside async is acceptable.
        out: list[list[float]] = []
        for text in texts:
            response = self._genai.embed_content(
                model=self._MODEL_ID,
                content=text,
                task_type="retrieval_document",
            )
            out.append(list(response["embedding"]))
        return out

    async def embed_query(self, text: str) -> list[float]:
        response = self._genai.embed_content(
            model=self._MODEL_ID,
            content=text,
            task_type="retrieval_query",
        )
        return list(response["embedding"])


# ── Jina ────────────────────────────────────────────────────────────────────


class JinaEmbedder(EmbeddingProvider):
    """Jina AI ``embeddings-v3``.

    Multilingual, 1024-dim, supports task-specific encoding
    (``retrieval.passage`` / ``retrieval.query``). API key from
    ``JINA_API_KEY`` env var.

    Uses httpx (already a core dep); no extra install needed.
    """

    _ENDPOINT: str = "https://api.jina.ai/v1/embeddings"
    _MODEL_ID: str = "jina-embeddings-v3"
    _DIMENSION: int = 1024

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
                "Jina embedder needs an API key. Set JINA_API_KEY env var or pass api_key=...",
            )
        self._key = key
        self._model = model or self._MODEL_ID
        self._timeout = timeout_seconds

    @property
    def name(self) -> EmbedderName:
        return "jina"

    @property
    def dimension(self) -> int:
        return self._DIMENSION

    @property
    def supports_multilingual(self) -> bool:
        return True

    async def _call(self, texts: Sequence[str], *, task: str) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "task": task,
                    "input": list(texts),
                },
            )
            response.raise_for_status()
            data = response.json()
        return [list(item["embedding"]) for item in data["data"]]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._call(texts, task="retrieval.passage")

    async def embed_query(self, text: str) -> list[float]:
        result = await self._call([text], task="retrieval.query")
        return result[0]


# ── Ollama ──────────────────────────────────────────────────────────────────


class OllamaEmbedder(EmbeddingProvider):
    """Local Ollama HTTP API.

    Default model ``nomic-embed-text`` (768-dim, multilingual variant exists).
    Configurable via ``model`` / ``host`` arguments or ``OLLAMA_HOST`` env var.

    Uses httpx (core dep). The model must be pulled first
    (``ollama pull nomic-embed-text``).
    """

    def __init__(
        self,
        *,
        model: str = "nomic-embed-text",
        host: str | None = None,
        dimension: int | None = None,
        timeout_seconds: float = 60.0,
        supports_multilingual: bool = False,
    ) -> None:
        self._model = model
        self._host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self._dimension = dimension if dimension is not None else 768
        self._timeout = timeout_seconds
        self._multilingual = supports_multilingual

    @property
    def name(self) -> EmbedderName:
        return "ollama"

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def supports_multilingual(self) -> bool:
        return self._multilingual

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            out: list[list[float]] = []
            for text in texts:
                response = await client.post(
                    f"{self._host}/api/embed",
                    json={"model": self._model, "input": text},
                )
                response.raise_for_status()
                data = response.json()
                # Ollama returns either ``embeddings`` (list-of-list) or
                # ``embedding`` (single list) depending on version.
                if "embeddings" in data:
                    out.append(list(data["embeddings"][0]))
                else:
                    out.append(list(data["embedding"]))
        return out


# ── Gemma (SelfFork Reflex pillar) ──────────────────────────────────────────


class GemmaEmbedder(EmbeddingProvider):
    """Use the SelfFork Reflex mlx-server's hidden-state pooling.

    **Experimental.** Q4_0 quantisation was not embedding-tuned; quality
    against BGE-M3 / Jina v3 has not been validated. Useful only when the
    operator explicitly wants embedder + Reflex on a single model.

    Hits the orchestrator's mlx-server at ``runtime.host:port``.
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8080,
        dimension: int = 2048,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._base_url = f"http://{host}:{port}"
        self._dimension = dimension
        self._timeout = timeout_seconds

    @property
    def name(self) -> EmbedderName:
        return "gemma"

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            out: list[list[float]] = []
            for text in texts:
                response = await client.post(
                    f"{self._base_url}/v1/embeddings",
                    json={"input": text},
                )
                response.raise_for_status()
                data = response.json()
                out.append(list(data["data"][0]["embedding"]))
        return out


# ── Factory ─────────────────────────────────────────────────────────────────


def build_embedder(name: EmbedderName, **kwargs: object) -> EmbeddingProvider:
    """Look up an embedder class by name and construct it.

    Raises :class:`ValueError` for unknown names. Concrete kwargs depend on
    the backend; see each class's ``__init__``.
    """
    table: dict[EmbedderName, type[EmbeddingProvider]] = {
        "bge-m3": BGEM3Embedder,
        "openai": OpenAIEmbedder,
        "gemini": GeminiEmbedder,
        "jina": JinaEmbedder,
        "ollama": OllamaEmbedder,
        "gemma": GemmaEmbedder,
    }
    cls = table.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown embedder {name!r}; expected one of {sorted(table)}",
        )
    return cls(**kwargs)
