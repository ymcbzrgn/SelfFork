"""Smoke test: package + all Order 1 sub-packages are importable."""

from __future__ import annotations


def test_package_imports() -> None:
    import selffork_mind

    assert selffork_mind.__version__ == "0.0.1"


def test_public_api_exports() -> None:
    from selffork_mind import (
        DataPoint,
        Filter,
        FilterAll,
        FilterAny,
        FilterCondition,
        FilterNot,
        FilterOp,
        Note,
        NoteKind,
        RecallEvent,
        RecallReader,
        RecallSession,
        Tag,
        TagMatchMode,
        TierName,
    )

    assert DataPoint is not None
    assert Note is not None
    assert Tag is not None
    assert {TagMatchMode.ANY, TagMatchMode.ALL} == set(TagMatchMode)
    # Type aliases / Literal types exist as runtime objects.
    assert NoteKind is not None
    assert TierName is not None
    assert FilterOp is not None
    for cls in (FilterCondition, FilterAll, FilterAny, FilterNot):
        assert cls is not None
    assert Filter is not None
    # T6 Recall (Order 1 → Order 2 transition)
    assert RecallReader is not None
    assert RecallEvent is not None
    assert RecallSession is not None


def test_subpackages_import() -> None:
    import selffork_mind.compaction
    import selffork_mind.eval
    import selffork_mind.historian
    import selffork_mind.memory
    import selffork_mind.projections
    import selffork_mind.rag
    import selffork_mind.store

    for pkg in (
        selffork_mind.memory,
        selffork_mind.rag,
        selffork_mind.store,
        selffork_mind.projections,
        selffork_mind.eval,
        selffork_mind.compaction,
        selffork_mind.historian,
    ):
        assert pkg is not None
