"""Placeholder smoke test until step 11 (full e2e) lands.

Replaced in step 11 by `test_selffork_run_smoke.py` per ADR-001 §11 / §16.1.
For now we only assert that all 5 workspace packages import cleanly,
which is the minimum the bootstrap commit must guarantee.
"""

from __future__ import annotations


def test_imports_root_workspace() -> None:
    """All 5 workspace packages must import cleanly from the root venv."""
    import selffork_body
    import selffork_mind
    import selffork_orchestrator
    import selffork_reflex
    import selffork_shared

    for pkg in (
        selffork_body,
        selffork_mind,
        selffork_orchestrator,
        selffork_reflex,
        selffork_shared,
    ):
        assert pkg.__version__ == "0.0.1", f"unexpected version on {pkg.__name__}"
