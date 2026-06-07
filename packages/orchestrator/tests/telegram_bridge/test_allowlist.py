"""Tests for :class:`AllowList`."""

from __future__ import annotations

import json
from pathlib import Path

from selffork_orchestrator.telegram.allowlist import (
    AllowList,
    AllowListConfig,
    default_allowlist_path,
)


def test_default_allowlist_path_under_home() -> None:
    assert default_allowlist_path() == Path.home() / ".selffork" / "operators.json"


def test_load_returns_empty_when_missing(tmp_path: Path) -> None:
    al = AllowList.load(AllowListConfig(path=tmp_path / "nope.json"))
    assert al.chat_ids == frozenset()
    assert al.default_project_slug is None
    assert al.is_allowed(123) is False


def test_load_parses_chat_ids(tmp_path: Path) -> None:
    path = tmp_path / "ops.json"
    path.write_text(
        json.dumps({"chat_ids": [11, 22, 33], "default_project_slug": "demo"}),
        encoding="utf-8",
    )
    al = AllowList.load(AllowListConfig(path=path))
    assert al.chat_ids == frozenset({11, 22, 33})
    assert al.default_project_slug == "demo"
    assert al.is_allowed(22) is True
    assert al.is_allowed(99) is False


def test_load_skips_non_int_chat_ids(tmp_path: Path) -> None:
    path = tmp_path / "ops.json"
    path.write_text(
        json.dumps({"chat_ids": [11, "twenty-two", 33, True]}),
        encoding="utf-8",
    )
    al = AllowList.load(AllowListConfig(path=path))
    # Booleans are technically int subclass; we filter them out.
    assert al.chat_ids == frozenset({11, 33})


def test_load_handles_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "ops.json"
    path.write_text("not json", encoding="utf-8")
    al = AllowList.load(AllowListConfig(path=path))
    assert al.chat_ids == frozenset()


def test_load_handles_non_object_root(tmp_path: Path) -> None:
    path = tmp_path / "ops.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    al = AllowList.load(AllowListConfig(path=path))
    assert al.chat_ids == frozenset()
