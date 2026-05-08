"""Filter DSL for Mind retrieval.

Per ADR-002 §5 — adapt mem0's payload-level filter DSL
(``examples_crucial/mem0/mem0/memory/main.py:1239-1314``).

Composable, JSON-serialisable, type-safe. The store backends evaluate filters
themselves (DuckDB SQL, LanceDB pyarrow predicate, Kuzu Cypher) so callers
never write SQL strings.

Example::

    f = FilterAll(
        FilterCondition("tier", "eq", "episodic"),
        FilterCondition("project_slug", "eq", "selffork"),
        FilterAny(
            FilterCondition("kind", "eq", "decision"),
            FilterCondition("kind", "eq", "pattern"),
        ),
        FilterNot(FilterCondition("pinned", "eq", True)),
    )

This is the only call surface — backends translate it to their native
predicate language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "Filter",
    "FilterAll",
    "FilterAny",
    "FilterCondition",
    "FilterNot",
    "FilterOp",
]


FilterOp = Literal[
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "in_",
    "nin",
    "contains",
    "icontains",
]
"""Operator literal — ``in_`` because ``in`` is a Python keyword.

mem0 uses ``in``/``nin`` as JSON keys; we expose ``in_``/``nin`` to keep
Python-side construction valid, then translate to JSON strings during
serialisation.
"""


@dataclass(frozen=True, slots=True)
class FilterCondition:
    """A single ``field <op> value`` predicate.

    ``contains`` / ``icontains`` apply to string fields (case-sensitive /
    insensitive). ``in_`` / ``nin`` take an iterable of values.
    """

    field: str
    op: FilterOp
    value: object

    def to_json(self) -> dict[str, object]:
        """JSON-serialisable form (``in_`` → ``in``)."""
        op = "in" if self.op == "in_" else self.op
        return {"field": self.field, "op": op, "value": self.value}


@dataclass(frozen=True, slots=True)
class FilterAll:
    """Conjunction (AND) of one or more filters."""

    children: tuple[Filter, ...] = field(default_factory=tuple)

    def __init__(self, *children: Filter) -> None:
        object.__setattr__(self, "children", tuple(children))

    def to_json(self) -> dict[str, object]:
        return {"all": [c.to_json() for c in self.children]}


@dataclass(frozen=True, slots=True)
class FilterAny:
    """Disjunction (OR) of one or more filters."""

    children: tuple[Filter, ...] = field(default_factory=tuple)

    def __init__(self, *children: Filter) -> None:
        object.__setattr__(self, "children", tuple(children))

    def to_json(self) -> dict[str, object]:
        return {"any": [c.to_json() for c in self.children]}


@dataclass(frozen=True, slots=True)
class FilterNot:
    """Negation of a single filter."""

    child: Filter

    def to_json(self) -> dict[str, object]:
        return {"not": self.child.to_json()}


type Filter = FilterCondition | FilterAll | FilterAny | FilterNot
"""A filter is either a leaf condition or a logical combinator over filters."""
