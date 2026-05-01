"""Smoke test: skeleton package is importable."""

from __future__ import annotations


def test_package_imports() -> None:
    import selffork_body

    assert selffork_body.__version__ == "0.0.1"
