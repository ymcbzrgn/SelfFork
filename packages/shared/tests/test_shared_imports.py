"""Smoke test: package is importable."""

from __future__ import annotations


def test_package_imports() -> None:
    import selffork_shared

    assert selffork_shared.__version__ == "0.0.1"
