"""ULID generation for correlation IDs and session IDs.

Thin wrapper around :mod:`ulid`. Kept as its own module so callers can
generate IDs without importing structlog or the rest of the shared package.

ULID format: 26 characters, Crockford base32, time-sortable, URL-safe.
"""

from __future__ import annotations

from ulid import ULID

__all__ = ["new_ulid"]


def new_ulid() -> str:
    """Generate a fresh ULID as a 26-character string.

    Use for correlation IDs (per top-level invocation) and session IDs
    (per ``selffork run``). Sortable by creation time.
    """
    return str(ULID())
