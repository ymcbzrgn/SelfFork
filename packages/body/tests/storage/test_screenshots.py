"""ScreenshotStore tests — write dedup + path layout + retention sweep."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from selffork_body.storage import ScreenshotRef, ScreenshotStore


@pytest.fixture()
def store(tmp_path):
    return ScreenshotStore(root=tmp_path)


def _png_bytes(seed: bytes = b"x") -> bytes:
    # Minimal but distinct PNG-shaped payload (header magic + content).
    return b"\x89PNG\r\n\x1a\n" + seed * 32


def test_write_returns_ref_with_metadata(store: ScreenshotStore) -> None:
    img = _png_bytes()
    ref = store.write(img, "session-A")
    assert isinstance(ref, ScreenshotRef)
    assert ref.session_id == "session-A"
    assert ref.project_slug is None
    assert ref.bytes_size == len(img)
    assert ref.sha256 == hashlib.sha256(img).hexdigest()
    assert ref.path.exists()
    assert ref.path.read_bytes() == img


def test_orphan_path_layout(store: ScreenshotStore, tmp_path) -> None:
    img = _png_bytes()
    ref = store.write(img, "session-orphan")
    assert "screenshots" in ref.path.parts
    assert "orphan" in ref.path.parts
    assert ref.path.parent.name == "session-orphan"


def test_project_path_layout(store: ScreenshotStore, tmp_path) -> None:
    img = _png_bytes()
    ref = store.write(img, "session-1", project_slug="myproj")
    parts = ref.path.parts
    assert "projects" in parts
    assert "myproj" in parts
    assert "screenshots" in parts
    assert ref.path.parent.name == "session-1"


def test_dedup_same_bytes_same_timestamp(store: ScreenshotStore) -> None:
    img = _png_bytes()
    ts = datetime.now(UTC)
    ref1 = store.write(img, "s", timestamp=ts)
    ref2 = store.write(img, "s", timestamp=ts)
    assert ref1.path == ref2.path
    assert ref1.sha256 == ref2.sha256


def test_distinct_bytes_distinct_path(store: ScreenshotStore) -> None:
    ts = datetime.now(UTC)
    ref1 = store.write(_png_bytes(b"a"), "s", timestamp=ts)
    ref2 = store.write(_png_bytes(b"b"), "s", timestamp=ts)
    assert ref1.path != ref2.path
    assert ref1.sha256 != ref2.sha256


def test_empty_bytes_raise(store: ScreenshotStore) -> None:
    with pytest.raises(ValueError):
        store.write(b"", "s")


def test_cleanup_invalid_retention(store: ScreenshotStore) -> None:
    with pytest.raises(ValueError):
        store.cleanup(retention_days=0)
    with pytest.raises(ValueError):
        store.cleanup(retention_days=-1)


def test_cleanup_removes_old_screenshots(store: ScreenshotStore) -> None:
    img = _png_bytes()
    ref = store.write(img, "s")
    # Backdate mtime to 30 days ago
    old_ts = (datetime.now(UTC) - timedelta(days=30)).timestamp()
    import os
    os.utime(ref.path, (old_ts, old_ts))
    fresh = store.write(_png_bytes(b"z"), "s")
    removed = store.cleanup(retention_days=7)
    assert removed == 1
    assert not ref.path.exists()
    assert fresh.path.exists()


def test_cleanup_no_op_when_empty(tmp_path) -> None:
    store = ScreenshotStore(root=tmp_path)
    assert store.cleanup(retention_days=7) == 0
