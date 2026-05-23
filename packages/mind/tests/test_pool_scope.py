"""Unit tests for ADR-009 §1 PoolScope primitive + group_id derivation."""

from __future__ import annotations

import pytest

from selffork_mind.store.base import (
    GLOBAL_GROUP_ID,
    PoolScope,
    derive_group_id,
    project_group_id,
)


class TestProjectGroupId:
    def test_simple_slug(self) -> None:
        assert project_group_id("selffork") == "p:selffork"

    def test_slug_with_dashes(self) -> None:
        assert project_group_id("m4-smoke-test") == "p:m4-smoke-test"

    def test_empty_slug_raises(self) -> None:
        with pytest.raises(ValueError, match="project_slug cannot be empty"):
            project_group_id("")


class TestDeriveGroupId:
    def test_explicit_group_id_wins(self) -> None:
        assert derive_group_id(group_id="g:global", project_slug="foo") == "g:global"

    def test_project_only_coalesces(self) -> None:
        assert derive_group_id(group_id=None, project_slug="selffork") == "p:selffork"

    def test_both_none_returns_none(self) -> None:
        assert derive_group_id(group_id=None, project_slug=None) is None

    def test_empty_string_project_treated_as_none(self) -> None:
        # An empty string is falsy; derive_group_id returns None rather
        # than raising — the project_group_id call only happens when
        # there's actually a slug.
        assert derive_group_id(group_id=None, project_slug="") is None


class TestPoolScope:
    def test_project_only_expands_to_single_group(self) -> None:
        scope = PoolScope(project_slug="selffork")
        assert scope.group_ids() == ("p:selffork",)
        assert scope.has_project()
        assert not scope.has_global()

    def test_global_only_expands_to_single_group(self) -> None:
        scope = PoolScope(include_global=True)
        assert scope.group_ids() == ("g:global",)
        assert scope.has_global()
        assert not scope.has_project()

    def test_project_plus_global_expands_to_both(self) -> None:
        scope = PoolScope(project_slug="selffork", include_global=True)
        assert scope.group_ids() == ("p:selffork", GLOBAL_GROUP_ID)
        assert scope.has_project()
        assert scope.has_global()

    def test_empty_scope_returns_empty_tuple(self) -> None:
        scope = PoolScope()
        assert scope.group_ids() == ()
        assert not scope.has_project()
        assert not scope.has_global()

    def test_pool_scope_is_immutable(self) -> None:
        scope = PoolScope(project_slug="foo")
        with pytest.raises((AttributeError, Exception)):
            scope.project_slug = "bar"  # type: ignore[misc]

    def test_global_group_id_literal(self) -> None:
        # Lock the literal so renames have to ripple through every callsite.
        assert GLOBAL_GROUP_ID == "g:global"
