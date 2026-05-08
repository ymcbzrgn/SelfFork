"""L3 Semantic clustering (ADR-002 §4).

Deterministic medoid clustering. **No LLM, no random init.** Two flavours:

- When notes carry stored embeddings, distance is cosine over the
  vectors. The cluster representative (medoid) is the note with the
  smallest mean distance to its peers.
- When embeddings are unavailable (Order 2 default `embedder=none`),
  distance falls back to **Jaccard distance over token sets** of the
  note content — adequate for de-duplication of near-identical notes
  (e.g. paraphrased decisions, retried tool sequences).

The strategy emits ``NoteCluster`` records — caller may supersede non-
representatives when applying the plan. ``representative_id`` is always
in ``member_ids``.

Algorithm: classic single-pass agglomerative — start each note in its
own cluster, then for each pair below the configured ``distance_cutoff``,
merge clusters greedily by smallest-distance-first. ``O(n² · d)`` over
the candidate window; n is bounded by the retriever's pre-fetch
(typically ≤500), so wall-clock stays in ms.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from selffork_mind.compaction.base import (
    CompactionPlan,
    NoteCluster,
)
from selffork_mind.memory.model import Note
from selffork_mind.store.base import MindStore

__all__ = ["MedoidClusterCompactor"]


_TOKEN_RE = re.compile(r"[\w]+", flags=re.UNICODE)


class MedoidClusterCompactor:
    """L3 — group near-duplicates, keep one representative per cluster."""

    layer: Literal["cluster"] = "cluster"

    def __init__(
        self,
        *,
        store: MindStore,
        distance_cutoff: float = 0.25,
        min_cluster_size: int = 2,
    ) -> None:
        if not 0.0 < distance_cutoff < 1.0:
            raise ValueError("distance_cutoff must be in (0, 1)")
        if min_cluster_size < 2:
            raise ValueError("min_cluster_size must be ≥ 2")
        self._store = store
        self._cutoff = distance_cutoff
        self._min_size = min_cluster_size

    async def plan(
        self,
        *,
        notes: Sequence[Note],
    ) -> CompactionPlan:
        if len(notes) < self._min_size:
            return CompactionPlan(
                layer=self.layer,
                summary={"reason": "too_few_notes", "count": len(notes)},
            )
        # Try vector path; fall back to Jaccard if embeddings missing.
        vectors = await self._fetch_vectors([n for n in notes if not n.pinned])
        notes_in_play = [n for n in notes if not n.pinned]
        if not notes_in_play:
            return CompactionPlan(layer=self.layer, summary={"reason": "all_pinned"})

        distance: _CosineDistance | _JaccardDistance
        if vectors and len(vectors) == len(notes_in_play):
            distance = _CosineDistance(vectors=vectors)
            mode = "vector"
        else:
            token_sets: dict[object, set[str]] = {n.id: _tokenise(n.content) for n in notes_in_play}
            distance = _JaccardDistance(token_sets=token_sets)
            mode = "jaccard"

        clusters = _cluster_pairwise(
            notes=notes_in_play,
            distance=distance,
            cutoff=self._cutoff,
        )

        # Filter to the configured min size.
        kept = [c for c in clusters if len(c.member_ids) >= self._min_size]
        return CompactionPlan(
            layer=self.layer,
            clusters=tuple(kept),
            summary={
                "clusters_built": len(kept),
                "candidates": len(notes_in_play),
                "distance_mode": mode,
                "cutoff": self._cutoff,
            },
        )

    async def _fetch_vectors(
        self,
        notes: Sequence[Note],
    ) -> dict[str, tuple[float, ...]]:
        out: dict[str, tuple[float, ...]] = {}
        for note in notes:
            emb = await self._store.get_embedding(note.id)
            if emb is None:
                continue
            vector, _name = emb
            out[str(note.id)] = tuple(vector)
        return out


# ── Distance backends ───────────────────────────────────────────────────


class _CosineDistance:
    """Cosine distance over a fixed pool of vectors."""

    def __init__(self, *, vectors: dict[str, tuple[float, ...]]) -> None:
        self._vectors = vectors

    def __call__(self, a: Note, b: Note) -> float:
        va = self._vectors.get(str(a.id))
        vb = self._vectors.get(str(b.id))
        if va is None or vb is None or len(va) != len(vb):
            return 1.0
        dot = sum(x * y for x, y in zip(va, vb, strict=True))
        norm_a = sum(x * x for x in va) ** 0.5
        norm_b = sum(y * y for y in vb) ** 0.5
        if norm_a == 0.0 or norm_b == 0.0:
            return 1.0
        cos = dot / (norm_a * norm_b)
        return float(max(0.0, 1.0 - cos))


class _JaccardDistance:
    """Token-set Jaccard distance over per-note token sets."""

    def __init__(self, *, token_sets: dict[object, set[str]]) -> None:
        self._token_sets = token_sets

    def __call__(self, a: Note, b: Note) -> float:
        ta = self._token_sets.get(a.id, set())
        tb = self._token_sets.get(b.id, set())
        if not ta and not tb:
            return 1.0
        intersection = ta & tb
        union = ta | tb
        if not union:
            return 1.0
        jaccard = len(intersection) / len(union)
        return 1.0 - jaccard


# ── Clustering — pure, deterministic ────────────────────────────────────


def _cluster_pairwise(
    *,
    notes: Sequence[Note],
    distance: object,  # callable Note,Note -> float
    cutoff: float,
) -> list[NoteCluster]:
    """Single-link agglomerative clustering with a hard cutoff."""
    parents: dict[object, object] = {n.id: n.id for n in notes}

    def find(x: object) -> object:
        while parents[x] != x:
            parents[x] = parents[parents[x]]
            x = parents[x]
        return x

    def union(x: object, y: object) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parents[rx] = ry

    distances: list[tuple[float, Note, Note]] = []
    for i, a in enumerate(notes):
        for b in notes[i + 1 :]:
            d = float(distance(a, b))  # type: ignore[operator]
            if d <= cutoff:
                distances.append((d, a, b))
    # Smallest-first merge — single-link agglomerative.
    distances.sort(key=lambda item: item[0])
    for _, a, b in distances:
        union(a.id, b.id)

    groups: dict[object, list[Note]] = {}
    for note in notes:
        root = find(note.id)
        groups.setdefault(root, []).append(note)

    clusters: list[NoteCluster] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        # Medoid: argmin of mean distance to peers.
        best_idx = 0
        best_total = float("inf")
        for i, candidate in enumerate(members):
            total = 0.0
            for j, peer in enumerate(members):
                if i == j:
                    continue
                total += float(distance(candidate, peer))  # type: ignore[operator]
            if total < best_total:
                best_total = total
                best_idx = i
        rep = members[best_idx]
        clusters.append(
            NoteCluster(
                representative_id=rep.id,
                member_ids=tuple(m.id for m in members),
            ),
        )
    # Deterministic ordering: by representative_id stringification.
    clusters.sort(key=lambda c: str(c.representative_id))
    return clusters


def _tokenise(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text)}
