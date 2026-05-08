"""Tests for :mod:`selffork_mind.memory.tags`."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from selffork_mind.memory.tags import Tag, TagMatchMode


class TestTagMatchMode:
    def test_any_and_all_distinct(self) -> None:
        assert TagMatchMode.ANY.value == "any"
        assert TagMatchMode.ALL.value == "all"
        assert {TagMatchMode.ANY, TagMatchMode.ALL} == set(TagMatchMode)


class TestTag:
    def test_now_factory_sets_utc_timestamp(self) -> None:
        before = datetime.now(UTC)
        t = Tag.now(note_id=uuid4(), key="cli", value="claude-code")
        after = datetime.now(UTC)
        assert before <= t.created_at <= after
        assert t.created_at.tzinfo is UTC

    def test_tag_is_frozen(self) -> None:
        t = Tag.now(note_id=uuid4(), key="cli", value="claude-code")
        # frozen=True dataclass — assignment must raise.
        try:
            t.value = "gemini"  # type: ignore[misc]
        except (AttributeError, TypeError):
            return
        msg = "Tag should be immutable (frozen=True)"
        raise AssertionError(msg)
