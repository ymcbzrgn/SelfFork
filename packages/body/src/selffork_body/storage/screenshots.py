"""Screenshot persistence for the M5 Body pillar (ADR-005 §M5-D3).

Stores PNG bytes on disk under ``~/.selffork`` with SHA-256 dedup, exposes a
typed ref object, and runs a configurable retention sweep. Audit emit on
``body.observation`` carries only the path reference + sha — never the bytes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

__all__ = ["ScreenshotRef", "ScreenshotStore"]


@dataclass(frozen=True, slots=True)
class ScreenshotRef:
    """Typed handle for a persisted screenshot.

    ``path`` is absolute and stable; the file is content-addressed via
    ``sha256`` (8-char prefix appears in the filename for human readability).
    """

    path: Path
    sha256: str
    timestamp: datetime
    session_id: str
    project_slug: str | None
    bytes_size: int


class ScreenshotStore:
    """Disk-backed screenshot store with SHA-256 dedup and retention sweep.

    Path layout::

        ~/.selffork/projects/<slug>/screenshots/<session_id>/<ts>_<sha8>.png
        ~/.selffork/screenshots/orphan/<session_id>/<ts>_<sha8>.png

    The store is a thin filesystem wrapper — no database, no index. Lookups
    are by ``ScreenshotRef`` returned at write time. Cockpit Body tab loads
    by path; audit JSONL stamps the path on ``body.observation`` events.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = (root or Path.home() / ".selffork").expanduser()

    @property
    def root(self) -> Path:
        return self._root

    def _dir_for(self, session_id: str, project_slug: str | None) -> Path:
        if project_slug:
            return self._root / "projects" / project_slug / "screenshots" / session_id
        return self._root / "screenshots" / "orphan" / session_id

    def write(
        self,
        image_bytes: bytes,
        session_id: str,
        *,
        project_slug: str | None = None,
        timestamp: datetime | None = None,
    ) -> ScreenshotRef:
        """Persist ``image_bytes`` and return a typed ref.

        Idempotent: writing identical bytes for the same session at the same
        timestamp yields the same path (sha8-based filename collision-free
        within a microsecond resolution).
        """
        if not image_bytes:
            raise ValueError("image_bytes must be non-empty")
        ts = timestamp or datetime.now(UTC)
        sha256 = hashlib.sha256(image_bytes).hexdigest()
        sha8 = sha256[:8]
        directory = self._dir_for(session_id, project_slug)
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{ts.strftime('%Y%m%dT%H%M%S%f')}_{sha8}.png"
        path = directory / filename
        if not path.exists():
            path.write_bytes(image_bytes)
        return ScreenshotRef(
            path=path,
            sha256=sha256,
            timestamp=ts,
            session_id=session_id,
            project_slug=project_slug,
            bytes_size=len(image_bytes),
        )

    def cleanup(self, retention_days: int = 7) -> int:
        """Delete screenshot files older than ``retention_days``.

        Returns count of removed files. Walks both ``projects/*/screenshots``
        and ``screenshots/orphan`` trees; ignores non-PNG files defensively.
        """
        if retention_days <= 0:
            raise ValueError("retention_days must be positive")
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        removed = 0
        for tree in (self._root / "projects", self._root / "screenshots" / "orphan"):
            if not tree.exists():
                continue
            for png in tree.rglob("*.png"):
                try:
                    mtime = datetime.fromtimestamp(png.stat().st_mtime, tz=UTC)
                except OSError:
                    continue
                if mtime < cutoff:
                    try:
                        png.unlink()
                        removed += 1
                    except OSError:
                        pass
        return removed
