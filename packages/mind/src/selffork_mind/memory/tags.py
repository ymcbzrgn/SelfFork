"""Tag junction primitive (Letta pattern, ``services/passage_manager.py:48-85``).

Tags are first-class many-to-many relations between :class:`~selffork_mind.memory.model.Note`
and a freeform key. The junction table enables ``DISTINCT`` across multi-tag
queries and ``match_mode = any | all`` predicates without slow JSON
contains-style scans.

Why a separate type rather than a string list:

- Letta's tag dimensions in SelfFork are ``(project, session, cli, decision,
  topic, severity)`` — six axes. A typed key + value tuple avoids string
  conventions like ``"cli:claude-code"`` that go stale.
- ``TagMatchMode`` flips between AND-of-tags and OR-of-tags at query time.
- Tags are written and queried by the store; this module is the schema only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

__all__ = [
    "Tag",
    "TagMatchMode",
]


class TagMatchMode(StrEnum):
    """Match semantics for multi-tag queries.

    Direct port of Letta's ``tag_match_mode`` enum
    (``examples_crucial/letta/letta/services/agent_manager.py:2430``).
    """

    ANY = "any"
    """Note matches if it carries at least one of the requested tags."""

    ALL = "all"
    """Note matches only if it carries every requested tag."""


@dataclass(frozen=True, slots=True)
class Tag:
    """A typed many-to-many edge between a :class:`Note` and a key/value pair.

    Tag identity is the ``(note_id, key, value)`` triple — the same note
    cannot carry two tags with the same key/value. The store enforces that
    via a unique index.
    """

    note_id: UUID
    key: str
    value: str
    created_at: datetime

    @classmethod
    def now(cls, *, note_id: UUID, key: str, value: str) -> Self:
        """Construct a tag with ``created_at = now()`` UTC."""
        return cls(
            note_id=note_id,
            key=key,
            value=value,
            created_at=datetime.now(UTC),
        )
