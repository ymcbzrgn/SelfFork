"""Filesystem persistence for :class:`HandoffBundle`.

Layout::

    ~/.selffork/projects/<slug>/sessions/<sid>/handoff/
      bundle-<bundle_id>.json

For orphan sessions (no project)::

    ~/.selffork/sessions/<sid>/handoff/
      bundle-<bundle_id>.json

Atomic write (tempfile + os.replace) to prevent torn reads.
"""
from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from selffork_orchestrator.handoff.bundle import HandoffBundle

__all__ = ["HandoffBundleStore", "default_handoff_root"]


def default_handoff_root() -> Path:
    """Top-level directory where handoff bundles live: ``~/.selffork``."""
    return Path.home() / ".selffork"


class HandoffBundleStore:
    """Filesystem-backed CRUD for :class:`HandoffBundle` records."""

    def __init__(self, *, root: Path | None = None) -> None:
        self._root = root if root is not None else default_handoff_root()

    @property
    def root(self) -> Path:
        return self._root

    # ── Path helpers ─────────────────────────────────────────────────────

    def session_dir(self, *, session_id: str, project_slug: str | None) -> Path:
        if project_slug:
            return (
                self._root
                / "projects"
                / project_slug
                / "sessions"
                / session_id
                / "handoff"
            )
        return self._root / "sessions" / session_id / "handoff"

    def bundle_path(
        self,
        *,
        session_id: str,
        bundle_id: str,
        project_slug: str | None,
    ) -> Path:
        return self.session_dir(
            session_id=session_id,
            project_slug=project_slug,
        ) / f"bundle-{bundle_id}.json"

    # ── CRUD ─────────────────────────────────────────────────────────────

    def save(self, bundle: HandoffBundle) -> Path:
        """Atomically persist ``bundle``; returns the file path."""
        path = self.bundle_path(
            session_id=bundle.session_id,
            bundle_id=bundle.bundle_id,
            project_slug=bundle.project_slug,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(bundle.model_dump_json(indent=2))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp_path)
            raise
        return path

    def load(
        self,
        *,
        session_id: str,
        bundle_id: str,
        project_slug: str | None = None,
    ) -> HandoffBundle | None:
        """Read a bundle by id; returns ``None`` for missing / malformed files."""
        path = self.bundle_path(
            session_id=session_id,
            bundle_id=bundle_id,
            project_slug=project_slug,
        )
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            return HandoffBundle.model_validate_json(text)
        except ValidationError:
            return None

    def list_for_session(
        self,
        *,
        session_id: str,
        project_slug: str | None = None,
    ) -> list[HandoffBundle]:
        """All bundles for ``session_id`` in mtime order (oldest first)."""
        d = self.session_dir(session_id=session_id, project_slug=project_slug)
        if not d.is_dir():
            return []
        records: list[tuple[float, HandoffBundle]] = []
        for path in d.glob("bundle-*.json"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                bundle = HandoffBundle.model_validate_json(text)
            except ValidationError:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            records.append((mtime, bundle))
        records.sort(key=lambda x: x[0])
        return [b for _, b in records]

    def remove(
        self,
        *,
        session_id: str,
        bundle_id: str,
        project_slug: str | None = None,
    ) -> bool:
        """Delete a bundle. Returns ``True`` if it existed."""
        path = self.bundle_path(
            session_id=session_id,
            bundle_id=bundle_id,
            project_slug=project_slug,
        )
        if not path.exists():
            return False
        path.unlink()
        return True
