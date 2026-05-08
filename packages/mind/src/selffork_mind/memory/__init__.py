"""SelfFork Mind memory primitives — schema, filters, tags.

Per ADR-002 §1-§2. Six tier modules land progressively (Order 2-5);
Order 1 ships the schema + filter DSL + tag junction.
"""

from __future__ import annotations

from selffork_mind.memory.filters import (
    Filter,
    FilterAll,
    FilterAny,
    FilterCondition,
    FilterNot,
    FilterOp,
)
from selffork_mind.memory.model import (
    DataPoint,
    Embeddable,
    Note,
    NoteKind,
    TierName,
    compute_content_hash,
)
from selffork_mind.memory.tags import Tag, TagMatchMode

__all__ = [
    "DataPoint",
    "Embeddable",
    "Filter",
    "FilterAll",
    "FilterAny",
    "FilterCondition",
    "FilterNot",
    "FilterOp",
    "Note",
    "NoteKind",
    "Tag",
    "TagMatchMode",
    "TierName",
    "compute_content_hash",
]
