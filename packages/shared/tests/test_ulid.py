"""Unit tests for :mod:`selffork_shared.ulid`."""

from __future__ import annotations

import re

from selffork_shared.ulid import new_ulid

# Crockford base32 alphabet (excludes I, L, O, U). We assert the broader
# uppercase-alphanumeric set since python-ulid emits Crockford-conformant.
_ULID_RE = re.compile(r"^[0-9A-Z]{26}$")


def test_new_ulid_returns_26_char_string() -> None:
    u = new_ulid()
    assert isinstance(u, str)
    assert len(u) == 26


def test_new_ulid_is_uppercase_alphanumeric() -> None:
    u = new_ulid()
    assert _ULID_RE.match(u) is not None


def test_new_ulid_unique_across_many_calls() -> None:
    ids = {new_ulid() for _ in range(1000)}
    assert len(ids) == 1000


def test_new_ulid_is_time_sortable() -> None:
    # ULIDs generated later sort >= earlier ones.
    earlier = new_ulid()
    later = new_ulid()
    assert later >= earlier
