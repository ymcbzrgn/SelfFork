"""Tests for :mod:`selffork_mind.memory.model`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest

from selffork_mind.memory.model import (
    DataPoint,
    Embeddable,
    Note,
    compute_content_hash,
)


class TestComputeContentHash:
    def test_md5_hash_is_deterministic(self) -> None:
        assert compute_content_hash("hello") == compute_content_hash("hello")

    def test_different_content_different_hash(self) -> None:
        assert compute_content_hash("a") != compute_content_hash("b")

    def test_handles_non_ascii(self) -> None:
        # Turkish + emoji should both serialise cleanly.
        assert compute_content_hash("Yamaç ı 🚀") != compute_content_hash("yamac i")


class TestNoteIdentity:
    def test_identical_content_same_id(self) -> None:
        n1 = Note(
            tier="episodic",
            kind="observation",
            content="Operator prefers Pydantic over dataclass",
            session_id="s1",
        )
        n2 = Note(
            tier="episodic",
            kind="observation",
            content="Operator prefers Pydantic over dataclass",
            session_id="s1",
        )
        assert n1.id == n2.id

    def test_different_session_different_id(self) -> None:
        n1 = Note(
            tier="episodic",
            kind="observation",
            content="x",
            session_id="s1",
        )
        n2 = Note(
            tier="episodic",
            kind="observation",
            content="x",
            session_id="s2",
        )
        assert n1.id != n2.id

    def test_different_tier_different_id(self) -> None:
        n1 = Note(tier="episodic", kind="observation", content="x")
        n2 = Note(tier="procedural", kind="observation", content="x")
        assert n1.id != n2.id

    def test_content_hash_auto_populated(self) -> None:
        n = Note(tier="episodic", kind="observation", content="hello")
        assert n.content_hash == compute_content_hash("hello")


class TestNoteValidityWindow:
    def test_default_currently_valid(self) -> None:
        n = Note(tier="working", kind="observation", content="x")
        assert n.is_currently_valid() is True

    def test_future_valid_from_not_yet_valid(self) -> None:
        future = datetime.now(UTC) + timedelta(days=1)
        n = Note(
            tier="semantic_graph",
            kind="decision",
            content="x",
            valid_from=future,
        )
        assert n.is_currently_valid() is False

    def test_supersede_sets_valid_until(self) -> None:
        n = Note(tier="semantic_graph", kind="decision", content="x")
        moment = datetime.now(UTC)
        s = n.superseded(at=moment)
        assert s.valid_until == moment
        assert s.is_currently_valid(at=moment) is False
        # Original instance unchanged (model_copy semantics).
        assert n.valid_until is None

    def test_validity_window_validation(self) -> None:
        future = datetime.now(UTC) + timedelta(days=1)
        past = datetime.now(UTC) - timedelta(days=1)
        with pytest.raises(ValueError, match="precedes"):
            Note(
                tier="working",
                kind="observation",
                content="x",
                valid_from=future,
                valid_until=past,
            )


class TestEmbeddableMarker:
    def test_note_content_is_embeddable(self) -> None:
        assert "content" in Note.embeddable_fields()

    def test_subclass_with_explicit_marker(self) -> None:
        class MyDP(DataPoint):
            description: Annotated[str, Embeddable()]
            internal_id: str = ""
            identity_fields: tuple[str, ...] = ("description",)

        fields = MyDP.embeddable_fields()
        assert "description" in fields
        assert "internal_id" not in fields
