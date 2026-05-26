"""Test isolation for dashboard tests that boot ``build_app``.

The dashboard lifespan auto-boots the CodexBar sidecar and the
SnapperRunner; both touch the operator's real ``~/.selffork/`` tree
by default. This conftest disables those sidecars and points the
canonical CLI-state directory at a per-test tmp path so test suites
remain hermetic across machines.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_quota_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SELFFORK_SNAPPER_RUNNER_ENABLED", "false")
    monkeypatch.setenv("SELFFORK_CODEXBAR_ENABLED", "false")
    monkeypatch.setenv(
        "SELFFORK_CLI_STATE_DIR", str(tmp_path / "_isolated-cli-state"),
    )
