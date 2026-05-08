"""Smoke tests for :mod:`selffork_mind.rag` factory error paths.

Concrete embedder / reranker construction requires optional deps that may
not be installed in every CI image. These tests exercise the error
surface of :func:`build_embedder` / :func:`build_reranker` plus the
non-default Ollama/Jina paths that share httpx (always available).
"""

from __future__ import annotations

import pytest

from selffork_mind.rag import (
    OllamaEmbedder,
    build_embedder,
    build_reranker,
)


class TestBuildEmbedder:
    def test_unknown_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown embedder"):
            build_embedder("nope")  # type: ignore[arg-type]

    def test_ollama_constructs_without_remote_call(self) -> None:
        # Ollama backend uses httpx (core dep) — construction does not hit
        # the network.
        emb = build_embedder("ollama", model="nomic-embed-text", dimension=768)
        assert isinstance(emb, OllamaEmbedder)
        assert emb.dimension == 768
        assert emb.name == "ollama"

    def test_jina_requires_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("JINA_API_KEY", raising=False)
        with pytest.raises(ValueError, match="JINA_API_KEY"):
            build_embedder("jina")


class TestBuildReranker:
    def test_unknown_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown reranker"):
            build_reranker("nope")  # type: ignore[arg-type]

    def test_jina_requires_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("JINA_API_KEY", raising=False)
        with pytest.raises(ValueError, match="JINA_API_KEY"):
            build_reranker("jina")
