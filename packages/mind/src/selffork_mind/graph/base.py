"""Graph store Protocol + core types.

Per ADR-002 §1, §5, §6: T3 Semantic Graph holds bi-temporal facts as
triples ``(subject, predicate, object)``. Subjects/objects are
:class:`PhraseNode` ids (strings: lowercased, normalised); predicates are
short verb labels (``"uses"``, ``"supersedes"``, ``"located_in"``, …).

The store is intentionally narrow:

- Add / fetch / supersede triples.
- Index passage→phrase (the HippoRAG 2 contains-edge): a passage is
  itself a :class:`Note` (Episodic / Procedural / etc.); a phrase is a
  short normalised n-gram extracted from the passage's content.
- Personalised PageRank (PPR) seed expansion is exposed as a
  ``neighbours_within(...)`` walk so the high-level retriever can
  compute scores in pure Python.

Bi-temporal semantics mirror :class:`~selffork_mind.memory.model.Note`:
``valid_from`` / ``valid_until`` are stamped on every triple. Facts are
never mutated; supersession writes a new triple and stamps ``valid_until``
on the prior one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

__all__ = [
    "GraphTriple",
    "PhraseNode",
    "SemanticGraphStore",
]


@dataclass(frozen=True, slots=True)
class PhraseNode:
    """One phrase node — a normalised lexical unit (HippoRAG 2 phrase node).

    ``id`` is the normalised phrase text (lowercased, single-spaced,
    leading/trailing punctuation stripped). ``passage_ids`` is the set of
    :class:`Note` ids that contain this phrase — the contains-edge
    backbone of HippoRAG 2.
    """

    id: str
    passage_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class GraphTriple:
    """One bi-temporal ``(subject, predicate, obj)`` fact.

    Subjects and ``obj`` (object) are :class:`PhraseNode` ids. The
    triple's identity is its ``(subject, predicate, obj,
    source_passage_id)`` tuple — re-extracting the same triple from the
    same passage coalesces cleanly. ``source_passage_id`` is the
    originating :class:`Note` (Episodic round, Procedural pattern, etc.).

    The field is named ``obj`` (not ``object``) to avoid shadowing the
    Python builtin in dataclass type annotations; the wire format
    serialised by :meth:`to_payload` keeps the conventional
    ``"object"`` key.
    """

    subject: str
    predicate: str
    obj: str
    source_passage_id: UUID
    project_slug: str | None = None
    group_id: str | None = None
    """ADR-009 §1 dual-pool partition key (``p:<slug>`` / ``g:global``).

    When ``None``, read-time coalesces to ``p:<project_slug>`` if set;
    otherwise the triple belongs to the GLOBAL pool by default. The
    actual storage isolation lives in the per-pool Kuzu engines
    (:class:`~selffork_mind.store.pool.PoolResolver`) so this field is
    informational at the model level — useful for cross-pool merges
    when consolidators emit triples directly.
    """
    confidence: float = 1.0
    valid_from: datetime = field(default_factory=lambda: datetime.now(UTC))
    valid_until: datetime | None = None

    def is_currently_valid(self, *, at: datetime | None = None) -> bool:
        moment = at if at is not None else datetime.now(UTC)
        if moment < self.valid_from:
            return False
        if self.valid_until is None:
            return True
        return moment < self.valid_until

    def to_payload(self) -> dict[str, object]:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.obj,
            "source_passage_id": str(self.source_passage_id),
            "project_slug": self.project_slug,
            "group_id": self.group_id,
            "confidence": self.confidence,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": (self.valid_until.isoformat() if self.valid_until is not None else None),
        }


@runtime_checkable
class SemanticGraphStore(Protocol):
    """Storage backend Protocol for T3.

    All methods async — backends (in-memory, Kuzu) may be I/O-bound.
    """

    async def setup(self) -> None: ...

    async def teardown(self) -> None: ...

    # ── triples ────────────────────────────────────────────────────────

    async def add_triple(self, triple: GraphTriple) -> None: ...

    async def add_triples(self, triples: Sequence[GraphTriple]) -> None: ...

    async def supersede_triple(
        self,
        *,
        subject: str,
        predicate: str,
        object_: str,
        source_passage_id: UUID,
        at: datetime | None = None,
    ) -> bool: ...

    async def list_triples(
        self,
        *,
        project_slug: str | None = None,
        subject: str | None = None,
        predicate: str | None = None,
        object_: str | None = None,
        valid_at: datetime | None = None,
    ) -> list[GraphTriple]: ...

    # ── passage / phrase ───────────────────────────────────────────────

    async def add_passage(self, *, passage_id: UUID, phrases: Sequence[str]) -> None: ...

    async def list_phrases_for_passage(self, passage_id: UUID) -> list[str]: ...

    async def list_passages_for_phrase(self, phrase: str) -> list[UUID]: ...

    async def list_phrase_neighbours(
        self,
        phrase: str,
        *,
        max_hops: int = 2,
    ) -> list[str]: ...
