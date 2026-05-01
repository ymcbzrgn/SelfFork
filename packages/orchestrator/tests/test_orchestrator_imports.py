"""Smoke test: package is importable."""

from __future__ import annotations


def test_package_imports() -> None:
    import selffork_orchestrator

    assert selffork_orchestrator.__version__ == "0.0.1"
