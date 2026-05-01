"""Tests for :func:`build_plan_store`."""

from __future__ import annotations

from pathlib import Path

import pytest

from selffork_orchestrator.plan.factory import build_plan_store
from selffork_orchestrator.plan.store_filesystem import FilesystemPlanStore
from selffork_shared.config import PlanConfig


def test_filesystem_resolved(tmp_path: Path) -> None:
    cfg = PlanConfig(backend="filesystem")
    store = build_plan_store(cfg, workspace_path=str(tmp_path))
    assert isinstance(store, FilesystemPlanStore)


def test_git_stub_raises(tmp_path: Path) -> None:
    cfg = PlanConfig(backend="git")
    with pytest.raises(NotImplementedError):
        build_plan_store(cfg, workspace_path=str(tmp_path))
