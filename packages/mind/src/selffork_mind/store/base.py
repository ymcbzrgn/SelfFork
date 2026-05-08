"""``MindStore`` Protocol — the contract every storage backend implements.

Per ADR-002 §2 + §5. Backends:

- :class:`~selffork_mind.store.duckdb.DuckDBMindStore` (Order 1, reference impl).
- LanceDBMindStore (lands Order 2 with T2 Episodic vectors).
- KuzuMindStore (lands Order 4 with T3 Semantic Graph).

The Protocol is intentionally narrow: write notes, fetch by id, query with a
filter + optional vector + optional reranker. Higher-level retrievers
(:mod:`selffork_mind.rag.retriever`) compose stores with adaptive routing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from selffork_mind.memory.filters import Filter
from selffork_mind.memory.model import Note, TierName
from selffork_mind.memory.tags import Tag, TagMatchMode

__all__ = [
    "MindStore",
    "RetrievalHit",
    "RetrieveConfig",
    "StoreScope",
]


@dataclass(frozen=True, slots=True)
class StoreScope:
    """Multi-scope retrieval filter (mem0 pattern, ADR-002 §1).

    Mirrors mem0's ``user_id / agent_id / run_id / app_id`` axes adapted to
    SelfFork's first-class concepts. ``None`` on any field means "any value".
    """

    project_slug: str | None = None
    session_id: str | None = None
    cli_agent: str | None = None
    operator_id: str | None = None


@dataclass(frozen=True, slots=True)
class RetrieveConfig:
    """Inputs for a retrieval query.

    Stages:

    1. Filter + scope → candidate set.
    2. Optional vector similarity (when ``query_embedding`` is set).
    3. Optional rerank (caller passes the reranker; store returns top-N raw,
       caller does the reranking).

    Per ADR-002 §3b: when ``top_k`` candidates are needed and a reranker is
    available, the store returns ``top_k * rerank_overfetch`` candidates so
    the rerank stage has room to re-order.
    """

    tiers: tuple[TierName, ...] = ()
    """Tiers to query. Empty tuple means all tiers."""

    scope: StoreScope = field(default_factory=StoreScope)
    filter: Filter | None = None
    """Optional payload-level predicate (mem0 DSL)."""

    tag_pairs: tuple[tuple[str, str], ...] = ()
    """Each element is a ``(key, value)`` pair. Empty = no tag predicate.

    With :attr:`tag_match_mode` ``ANY``, a note matches if it carries at
    least one of the listed pairs. With ``ALL``, every pair must be
    present.
    """
    tag_match_mode: TagMatchMode = TagMatchMode.ANY

    query_embedding: tuple[float, ...] | None = None
    """When set, candidates are scored by cosine similarity."""

    top_k: int = 20
    rerank_overfetch: int = 4
    """Multiplier on top_k when a reranker will run downstream."""

    valid_at: datetime | None = None
    """Bi-temporal: only return notes whose validity window contains this instant.

    ``None`` = "now". Use a past timestamp to query historical state.
    """

    include_invalid: bool = False
    """When True, also returns superseded notes (their valid_until ≠ None)."""

    file_path: str | None = None
    """When set, applies path-scoped attachment globs (Cursor pattern).

    Notes with ``always_apply=True`` always pass; notes with non-empty
    ``path_scope`` pass only if at least one glob matches ``file_path``.
    """


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    """One row in a retrieval result.

    ``score`` is the raw similarity score from the store (cosine for vector,
    1.0 for filter-only matches). The reranker may override this downstream.
    """

    note: Note
    score: float
    matched_tags: tuple[Tag, ...] = ()


@runtime_checkable
class MindStore(Protocol):
    """Storage backend Protocol.

    All methods are async. Backends are expected to be safe for concurrent
    reads; concurrent writes use append-only semantics (notes are never
    mutated, validity windows are updated as new rows).
    """

    async def setup(self) -> None:
        """Create tables / indices / connection pool. Idempotent."""

    async def teardown(self) -> None:
        """Close connections. Idempotent."""

    # ── writes ─────────────────────────────────────────────────────────

    async def upsert_note(self, note: Note) -> Note:
        """Insert or update a note by id. Returns the stored note (with id populated)."""

    async def upsert_notes(self, notes: Sequence[Note]) -> list[Note]:
        """Batch upsert. Returns stored notes in input order."""

    async def supersede(
        self,
        note_id: UUID,
        *,
        at: datetime | None = None,
    ) -> Note | None:
        """Mark an existing note as superseded by stamping ``valid_until = at``.

        Returns the updated note, or None if id not found. ``at`` defaults
        to ``datetime.now(UTC)``.
        """

    async def attach_tag(self, tag: Tag) -> Tag:
        """Add a tag to a note. Idempotent on (note_id, key, value)."""

    async def attach_tags(self, tags: Sequence[Tag]) -> list[Tag]:
        """Batch tag attach."""

    async def detach_tag(self, *, note_id: UUID, key: str, value: str) -> bool:
        """Remove a tag. Returns True if a row was deleted."""

    # ── reads ──────────────────────────────────────────────────────────

    async def get_note(self, note_id: UUID) -> Note | None:
        """Fetch a single note by id."""

    async def get_notes(self, note_ids: Sequence[UUID]) -> list[Note]:
        """Batch fetch. Order matches input; missing ids are skipped silently."""

    async def list_tags(self, note_id: UUID) -> list[Tag]:
        """All tags attached to a note."""

    async def retrieve(self, config: RetrieveConfig) -> list[RetrievalHit]:
        """Run a retrieval query.

        Pipeline: filter + scope + tag-match + bi-temporal + path-scope →
        optional vector cosine ranking → cap at ``top_k * rerank_overfetch``.
        Caller is responsible for the rerank stage (it may not run a
        reranker at all).
        """

    # ── embeddings ─────────────────────────────────────────────────────

    async def attach_embedding(
        self,
        *,
        note_id: UUID,
        vector: Sequence[float],
        embedder_name: str,
    ) -> None:
        """Persist an embedding vector for an existing note.

        Embeddings are a side-channel to the canonical :class:`Note` record
        — adding/removing them never mutates note identity or content.
        Backends that don't support vector storage may treat this as a
        no-op (and :meth:`get_embedding` returns ``None``).
        """

    async def get_embedding(
        self,
        note_id: UUID,
    ) -> tuple[list[float], str] | None:
        """Return ``(vector, embedder_name)`` for a note, or ``None`` if absent."""
