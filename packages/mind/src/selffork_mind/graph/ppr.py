"""Personalized PageRank — pure Python.

Reference: Jiménez Gutiérrez et al. (2025), "From RAG to Memory:
Non-Parametric Continual Learning for Large Language Models" (HippoRAG 2,
ICML 2025, arXiv:2502.14802).

Single-source PPR over a phrase + passage bipartite graph. Used by
:class:`~selffork_mind.graph.retriever.GraphRetriever` to score passages
given a set of seed phrases extracted from the operator's query.

Implementation: power iteration with a teleport probability ``alpha``
back to the seed distribution. Deterministic — same seeds + same graph
shape always produce the same scores.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

__all__ = ["personalized_pagerank"]


def personalized_pagerank(
    *,
    seeds: Sequence[str],
    phrase_to_passages: Mapping[str, Sequence[UUID]],
    passage_to_phrases: Mapping[UUID, Sequence[str]],
    alpha: float = 0.5,
    iterations: int = 30,
    tolerance: float = 1e-6,
) -> dict[UUID, float]:
    """Run PPR seeded on ``seeds``; return a passage→score map.

    The graph is bipartite (phrase ↔ passage); each edge has uniform
    weight. ``alpha`` is the teleport probability back to the seed
    distribution. Higher ``alpha`` keeps more probability mass near the
    seeds (sharper, more local); lower ``alpha`` spreads further.

    Returns an empty mapping when no seed actually appears in
    ``phrase_to_passages`` (deterministic; no spurious scores).
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if iterations < 1:
        raise ValueError("iterations must be ≥ 1")

    # Build a unified ranking dict over both phrases and passages — we
    # walk the bipartite graph as a single random walk.
    seed_phrases = [s for s in seeds if s in phrase_to_passages]
    if not seed_phrases:
        return {}

    seed_mass = 1.0 / len(seed_phrases)
    teleport: dict[str | UUID, float] = {phrase: seed_mass for phrase in seed_phrases}

    rank: dict[str | UUID, float] = dict(teleport)

    for _ in range(iterations):
        new_rank: dict[str | UUID, float] = {}
        # Teleport portion.
        for node, mass in teleport.items():
            new_rank[node] = new_rank.get(node, 0.0) + alpha * mass
        # Walk portion.
        for node, mass in rank.items():
            neighbours = _neighbours(
                node,
                phrase_to_passages=phrase_to_passages,
                passage_to_phrases=passage_to_phrases,
            )
            if not neighbours:
                # Dangling node — return its mass to teleport.
                for seed in seed_phrases:
                    new_rank[seed] = new_rank.get(seed, 0.0) + (1 - alpha) * mass / len(
                        seed_phrases,
                    )
                continue
            share = (1 - alpha) * mass / len(neighbours)
            for neighbour in neighbours:
                new_rank[neighbour] = new_rank.get(neighbour, 0.0) + share

        # Convergence check.
        delta = sum(abs(new_rank.get(k, 0.0) - rank.get(k, 0.0)) for k in new_rank)
        rank = new_rank
        if delta < tolerance:
            break

    # Filter to passage scores only — the caller wants Notes, not phrases.
    return {node: score for node, score in rank.items() if isinstance(node, UUID)}


def _neighbours(
    node: str | UUID,
    *,
    phrase_to_passages: Mapping[str, Sequence[UUID]],
    passage_to_phrases: Mapping[UUID, Sequence[str]],
) -> list[str | UUID]:
    """Return the bipartite neighbours of ``node``."""
    if isinstance(node, UUID):
        return list(passage_to_phrases.get(node, ()))
    return list(phrase_to_passages.get(node, ()))
