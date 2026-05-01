"""ScheduledResumeStore — filesystem-backed persistence for paused sessions.

When :class:`Session.run_loop` detects a subscription rate-limit it
serializes a :class:`ScheduledResume` record under ``~/.selffork/scheduled/``
(or a configured root). The ``selffork resume`` commands read this
directory to list / show / resume / watch.

JSON layout (one file per scheduled resume, named ``<session_id>.json``):

    {
      "session_id":     "01KQHX...",
      "scheduled_at":   "2026-05-01T14:18:00Z",   # when we paused
      "resume_at":      "2026-05-01T19:00:00Z",   # earliest UTC retry moment
      "cli_agent":      "claude-code",
      "config_path":    "/abs/path/to/selffork.yaml",  # null if defaults
      "prd_path":       "/abs/path/to/prd.md",
      "workspace_path": "/abs/path/to/sandbox/<ulid>",  # informational
      "reason":         "claude usage limit reached; reset at 2pm America/New_York",
      "kind":           "rpd"                       # rpm | rpd | weekly | unknown
    }

Atomicity: writes go through ``tempfile.NamedTemporaryFile`` + rename,
so a crash mid-write never leaves a half-serialized file.

The store is intentionally **stateless across instances** — every
``ScheduledResumeStore(root=...)`` reads the directory fresh each call.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from selffork_shared.errors import SelfForkError

__all__ = [
    "ScheduledResume",
    "ScheduledResumeStore",
]


@dataclass(frozen=True, slots=True)
class ScheduledResume:
    """Serialized record of a paused session waiting on a quota window.

    All datetime fields are ISO-8601 with explicit ``Z`` UTC suffix when
    serialized; constructors accept aware datetimes only.
    """

    session_id: str
    scheduled_at: datetime
    resume_at: datetime
    cli_agent: str
    config_path: str | None
    prd_path: str
    workspace_path: str
    reason: str
    kind: str

    def to_json_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dict (datetimes → ISO strings)."""
        d = asdict(self)
        d["scheduled_at"] = self.scheduled_at.astimezone(UTC).isoformat()
        d["resume_at"] = self.resume_at.astimezone(UTC).isoformat()
        return d

    @classmethod
    def from_json_dict(cls, data: dict[str, object]) -> ScheduledResume:
        """Inverse of :meth:`to_json_dict`. Raises on malformed input."""
        try:
            return cls(
                session_id=str(data["session_id"]),
                scheduled_at=_parse_iso(str(data["scheduled_at"])),
                resume_at=_parse_iso(str(data["resume_at"])),
                cli_agent=str(data["cli_agent"]),
                config_path=(str(data["config_path"]) if data.get("config_path") else None),
                prd_path=str(data["prd_path"]),
                workspace_path=str(data["workspace_path"]),
                reason=str(data["reason"]),
                kind=str(data["kind"]),
            )
        except (KeyError, ValueError) as exc:
            raise SelfForkError(
                f"malformed ScheduledResume record: {type(exc).__name__}: {exc}",
            ) from exc

    def is_due(self, *, now: datetime | None = None) -> bool:
        """Return ``True`` when ``resume_at`` is in the past."""
        clock = now if now is not None else datetime.now(UTC)
        return clock >= self.resume_at


class ScheduledResumeStore:
    """Filesystem-backed CRUD for :class:`ScheduledResume` records."""

    def __init__(self, *, root: Path) -> None:
        self._root = root.expanduser()

    @property
    def root(self) -> Path:
        return self._root

    # ── CRUD ──────────────────────────────────────────────────────────

    def save(self, record: ScheduledResume) -> Path:
        """Atomically persist ``record``. Returns the file path written."""
        self._root.mkdir(parents=True, exist_ok=True)
        target = self._record_path(record.session_id)
        # Write to a temp file in the same directory, then rename — POSIX
        # rename is atomic when source and target are on the same FS.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self._root),
            prefix=f".{record.session_id}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(record.to_json_dict(), f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp_name, target)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise
        return target

    def load(self, session_id: str) -> ScheduledResume | None:
        """Return the record for ``session_id``, or ``None`` if missing."""
        target = self._record_path(session_id)
        if not target.is_file():
            return None
        with target.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise SelfForkError(
                f"ScheduledResume file is not an object: {target}",
            )
        return ScheduledResume.from_json_dict(data)

    def remove(self, session_id: str) -> bool:
        """Delete the record. Returns ``True`` if it existed."""
        target = self._record_path(session_id)
        if not target.is_file():
            return False
        target.unlink()
        return True

    def list_all(self) -> list[ScheduledResume]:
        """Load every record under root, sorted ascending by ``resume_at``.

        Skips malformed files with a warning rather than crashing the
        listing — partial corruption shouldn't break ``selffork resume list``.
        """
        records: list[ScheduledResume] = []
        for record in self._iter_records():
            records.append(record)
        records.sort(key=lambda r: r.resume_at)
        return records

    def list_due(self, *, now: datetime | None = None) -> list[ScheduledResume]:
        """Records whose ``resume_at`` is in the past relative to ``now``."""
        clock = now if now is not None else datetime.now(UTC)
        return [r for r in self.list_all() if r.is_due(now=clock)]

    # ── Internals ─────────────────────────────────────────────────────

    def _record_path(self, session_id: str) -> Path:
        return self._root / f"{session_id}.json"

    def _iter_records(self) -> Iterator[ScheduledResume]:
        if not self._root.is_dir():
            return
        for entry in sorted(self._root.iterdir()):
            if not entry.is_file() or not entry.name.endswith(".json"):
                continue
            if entry.name.startswith("."):
                # Skip in-progress temp files written by save().
                continue
            try:
                with entry.open(encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            try:
                yield ScheduledResume.from_json_dict(data)
            except SelfForkError:
                continue


def _parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 datetime string, normalizing trailing ``Z`` to UTC."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"datetime is naive: {s!r}")
    return dt.astimezone(UTC)
