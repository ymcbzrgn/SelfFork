"""Core schema primitives for SelfFork Mind.

Per ADR-002 §2 + §6:

- :class:`DataPoint` — base for any addressable memory unit. Identity is a
  deterministic UUID5 derived from ``identity_fields`` (Cognee pattern,
  ``examples_crucial/cognee/cognee/infrastructure/engine/models/DataPoint.py:104``).
  The ``Annotated[..., Embeddable()]`` field marker controls which fields are
  passed to the embedder (Cognee pattern, line 147).

- :class:`Note` — concrete tier-aware memory unit. Carries:
    - ``tier`` — one of :class:`TierName`.
    - ``content`` — the body text the embedder will see.
    - ``intent`` — short human-readable label (GCC pointer-not-payload pattern,
      ``examples_crucial/git-context-controller/scripts/gcc_commit.sh:84-89``).
    - ``content_hash`` — md5 dedup primitive (mem0 pattern,
      ``examples_crucial/mem0/mem0/memory/main.py:799``).
    - ``valid_from`` / ``valid_until`` — bi-temporal validity window
      (Graphiti pattern, arXiv 2501.13956). Facts are never mutated; they are
      superseded by writing a new fact and setting ``valid_until`` on the old.

- :class:`TierName` — string literal enum naming the six tiers.

- :class:`NoteKind` — coarse classification used by retrievers and compaction
  (decision / observation / pattern / reflection / pointer).

These are the only primitives needed in Order 1. Higher-order tiers (T3
Semantic Graph) will add :class:`Edge` and :class:`PhraseNode` in Order 4.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import NAMESPACE_OID, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "DataPoint",
    "Embeddable",
    "Note",
    "NoteKind",
    "TierName",
    "compute_content_hash",
]


TierName = Literal[
    "working",
    "episodic",
    "semantic_graph",
    "procedural",
    "reflection",
    "recall",
]
"""Six-tier names per ADR-002 §1. Literal-typed so misspellings are mypy errors."""


NoteKind = Literal[
    "decision",
    "observation",
    "pattern",
    "reflection",
    "pointer",
]
"""Coarse classification.

- ``decision`` — operator-style choice or rejection (e.g. "use BGE-M3 not OpenAI").
- ``observation`` — raw fact captured from a session (e.g. "tool call X failed with Y").
- ``pattern`` — generalised reflex pattern distilled from observations (T4 Procedural).
- ``reflection`` — higher-level synthesised insight (T5 Reflection).
- ``pointer`` — GCC-style pointer entry (hash + intent), full content lives in T6 Recall.
"""


@dataclass(frozen=True, slots=True)
class Embeddable:
    """Marker annotation: this field's value is fed to the embedder.

    Usage::

        class MyNote(DataPoint):
            content: Annotated[str, Embeddable()]
            internal_id: str  # not embeddable

    Mirrors Cognee's ``_Embeddable`` (``cognee/infrastructure/engine/models/DataPoint.py:147``).
    """


def compute_content_hash(content: str) -> str:
    """Deterministic md5 hash of UTF-8 content (mem0 dedup primitive).

    Reference: ``examples_crucial/mem0/mem0/memory/main.py:799``.
    """
    return hashlib.md5(content.encode("utf-8")).hexdigest()  # noqa: S324


class DataPoint(BaseModel):
    """Base for any addressable memory unit.

    Identity is a UUID5 derived from the values of ``identity_fields``. Two
    instances with identical identity-field values share the same ``id``;
    this is the dedup primitive across re-ingests (Cognee pattern,
    ``examples_crucial/cognee/cognee/infrastructure/engine/models/DataPoint.py:104``).

    Subclasses override :pyattr:`identity_fields` to declare which fields
    participate in identity (defaults to ``("content_hash",)`` so notes with
    identical content collapse to the same id).
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    id: UUID = Field(
        default_factory=lambda: UUID(int=0),
        description="UUID5 from identity_fields. Auto-computed by validator.",
    )
    schema_version: int = Field(
        default=1,
        ge=1,
        description="Bumped when on-disk shape changes incompatibly.",
    )

    identity_fields: tuple[str, ...] = Field(
        default=("content_hash",),
        description="Subclasses override; participates in UUID5 identity.",
        exclude=True,
    )

    @model_validator(mode="after")
    def _compute_id(self) -> DataPoint:
        if self.id != UUID(int=0):
            return self  # explicit id wins (e.g. round-trip from disk)
        seed = "|".join(str(getattr(self, f, "")) for f in self.identity_fields)
        object.__setattr__(self, "id", uuid5(NAMESPACE_OID, seed))
        return self

    @classmethod
    def embeddable_fields(cls) -> tuple[str, ...]:
        """Return field names marked with :class:`Embeddable`.

        Reads Pydantic v2's ``model_fields`` so the marker is detected the
        same way Pydantic itself processes ``Annotated`` metadata. Walking
        ``__annotations__`` directly drops marker objects on subclasses
        whose annotations are already evaluated by the time we look.
        """
        out: list[str] = []
        for name, info in cls.model_fields.items():
            for meta in info.metadata:
                if isinstance(meta, Embeddable):
                    out.append(name)
                    break
        return tuple(out)


class Note(DataPoint):
    """A tier-aware memory unit.

    Notes carry the bi-temporal validity window (Graphiti pattern): a fact is
    valid from ``valid_from`` (inclusive) until ``valid_until`` (exclusive).
    A new fact that supersedes an old one is written with ``valid_from`` =
    now, and the old one's ``valid_until`` is updated to that same instant.
    Facts are NEVER mutated in place; the supersession is itself a write.

    The ``path_scope`` field carries a Cursor-style glob list — Mind only
    injects this note into context when the operator is reading a file
    matching one of the globs.
    """

    tier: TierName
    kind: NoteKind
    content: Annotated[str, Embeddable()]
    intent: str = Field(
        default="",
        max_length=200,
        description="Short human label (GCC pointer-not-payload pattern).",
    )
    content_hash: str = Field(
        default="",
        description="md5 of content, computed on validation if empty.",
    )

    # Bi-temporal validity (Graphiti)
    valid_from: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Fact becomes true at this UTC instant.",
    )
    valid_until: datetime | None = Field(
        default=None,
        description="Fact superseded at this UTC instant; None = currently valid.",
    )

    # Provenance
    project_slug: str | None = Field(
        default=None,
        description="Project this note is scoped to; None = global.",
    )
    session_id: str | None = Field(
        default=None,
        description="Session that produced this note; None = manual.",
    )
    source_pointer: str | None = Field(
        default=None,
        description="GCC-style pointer (e.g. 'audit:<session_id>:<line>').",
    )

    # Path-scoped attachment (Cursor `.cursor/rules/*.mdc` `paths:` glob list)
    path_scope: tuple[str, ...] = Field(
        default=(),
        description="Glob patterns; Mind injects this note only when reading matching files.",
    )
    always_apply: bool = Field(
        default=False,
        description="True overrides path_scope and injects unconditionally.",
    )

    # Tag soft references; full Tag objects live in the join table.
    tag_keys: tuple[str, ...] = Field(
        default=(),
        description="Tag keys attached to this note (resolved via store).",
    )

    # Compaction signals
    importance: float = Field(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="L1 recency-decay score input; refreshed by memory replay.",
    )
    pinned: bool = Field(
        default=False,
        description="Manual pin overrides decay; never evicted by compaction.",
    )

    identity_fields: tuple[str, ...] = Field(
        default=("tier", "content_hash", "session_id"),
        exclude=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _populate_content_hash(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if not data.get("content_hash") and isinstance(data.get("content"), str):
            data["content_hash"] = compute_content_hash(data["content"])
        return data

    @model_validator(mode="after")
    def _validate_validity_window(self) -> Note:
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError(
                f"valid_until ({self.valid_until}) precedes valid_from ({self.valid_from})",
            )
        return self

    def is_currently_valid(self, *, at: datetime | None = None) -> bool:
        """Return True if this note's validity window contains ``at`` (default now)."""
        moment = at if at is not None else datetime.now(UTC)
        if moment < self.valid_from:
            return False
        if self.valid_until is None:
            return True
        return moment < self.valid_until

    def superseded(self, *, at: datetime | None = None) -> Note:
        """Return a copy of this note with ``valid_until`` set to ``at`` (default now)."""
        moment = at if at is not None else datetime.now(UTC)
        return self.model_copy(update={"valid_until": moment})
