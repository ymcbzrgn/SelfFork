"""Tests for :mod:`selffork_mind.memory.filters`."""

from __future__ import annotations

from selffork_mind.memory.filters import (
    FilterAll,
    FilterAny,
    FilterCondition,
    FilterNot,
)


class TestFilterCondition:
    def test_eq_serialises(self) -> None:
        c = FilterCondition("tier", "eq", "episodic")
        assert c.to_json() == {"field": "tier", "op": "eq", "value": "episodic"}

    def test_in_renames_to_in(self) -> None:
        # Python's "in" is a keyword, so the dataclass uses "in_"; the JSON
        # form drops the trailing underscore for SQL/wire compatibility.
        c = FilterCondition("kind", "in_", ["decision", "pattern"])
        assert c.to_json() == {
            "field": "kind",
            "op": "in",
            "value": ["decision", "pattern"],
        }

    def test_icontains_serialises(self) -> None:
        c = FilterCondition("content", "icontains", "yamac")
        assert c.to_json()["op"] == "icontains"


class TestFilterAll:
    def test_empty_serialises(self) -> None:
        assert FilterAll().to_json() == {"all": []}

    def test_two_children_serialise(self) -> None:
        f = FilterAll(
            FilterCondition("tier", "eq", "episodic"),
            FilterCondition("project_slug", "eq", "selffork"),
        )
        out = f.to_json()
        assert "all" in out
        children = out["all"]
        assert isinstance(children, list)
        assert len(children) == 2


class TestFilterAny:
    def test_two_children_or(self) -> None:
        f = FilterAny(
            FilterCondition("kind", "eq", "decision"),
            FilterCondition("kind", "eq", "pattern"),
        )
        out = f.to_json()
        assert "any" in out
        children = out["any"]
        assert isinstance(children, list)
        assert len(children) == 2


class TestFilterNot:
    def test_negates_inner(self) -> None:
        inner = FilterCondition("pinned", "eq", True)
        f = FilterNot(inner)
        assert f.to_json() == {"not": inner.to_json()}


class TestComposite:
    def test_three_levels_deep(self) -> None:
        f = FilterAll(
            FilterCondition("tier", "eq", "episodic"),
            FilterAny(
                FilterCondition("kind", "eq", "decision"),
                FilterCondition("kind", "eq", "pattern"),
            ),
            FilterNot(FilterCondition("pinned", "eq", True)),
        )
        out = f.to_json()
        assert isinstance(out["all"], list)
        children = out["all"]
        assert isinstance(children[1], dict)
        assert "any" in children[1]
        assert isinstance(children[2], dict)
        assert "not" in children[2]
