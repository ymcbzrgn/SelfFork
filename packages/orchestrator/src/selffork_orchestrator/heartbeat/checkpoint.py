"""Heartbeat checkpoint — Hexis ``{step, progress, next_action}`` pattern.

ADR-008 §4 + Hexis ``heartbeat_agentic.py:241-276`` checkpoint format:
when the daemon is interrupted (process restart, ``SELF_STOP`` action,
unhandled error) the latest state lands on disk so the *next* boot can
resume from a meaningful place instead of replaying the whole audit
log.

The schema is intentionally tiny (3 keys + timestamp):

* ``step`` — what phase we were in (``"perceive"``, ``"decide"``,
  ``"act"``, ``"record"``, ``"idle"``).
* ``progress`` — short status string for the operator's morning report.
* ``next_action`` — what to attempt first on resume (a
  :class:`LegalAction` value when known).

Wire format: single JSON file at
``~/.selffork/heartbeat/checkpoint.json``. The writer **never
overwrites a manually-edited checkpoint** unless explicitly forced —
matches Hexis ``heartbeat_agentic.py:254`` (only-if-null preserve).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "Checkpoint",
    "CheckpointWriter",
    "default_checkpoint_path",
]


_log = logging.getLogger(__name__)


class Checkpoint(BaseModel):
    """Daemon resume state — exactly the 4 fields Hexis writes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step: str
    progress: str
    next_action: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


def default_checkpoint_path() -> Path:
    return Path("~/.selffork/heartbeat/checkpoint.json").expanduser()


@dataclass(frozen=True, slots=True)
class CheckpointWriter:
    """Persist + load the latest :class:`Checkpoint`.

    ``write`` is atomic via ``write_text`` to a temp sibling +
    ``rename``: an interrupted write never corrupts the on-disk JSON.
    ``write_unless_manual`` mirrors Hexis ``only-if-null`` — useful
    when the operator has scribbled a manual recovery note into the
    file and we don't want to clobber it.
    """

    path: Path

    def write(self, checkpoint: Checkpoint) -> None:
        """Atomically persist ``checkpoint`` to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
        temp.replace(self.path)

    def write_unless_manual(self, checkpoint: Checkpoint) -> bool:
        """Write only if no checkpoint exists; return ``True`` on write.

        Preserves an operator's manual notes (Hexis-style). Callers
        that need an overwrite use :meth:`write` directly.
        """
        if self.path.is_file():
            return False
        self.write(checkpoint)
        return True

    def read(self) -> Checkpoint | None:
        """Return the persisted checkpoint, or ``None`` when absent / bad."""
        if not self.path.is_file():
            return None
        try:
            raw = self.path.read_text(encoding="utf-8")
            return Checkpoint.model_validate_json(raw)
        except (OSError, ValueError) as exc:
            _log.warning(
                "heartbeat_checkpoint_read_failed",
                extra={"path": str(self.path), "error": str(exc)},
            )
            return None

    def clear(self) -> None:
        """Remove the checkpoint file (post-success cleanup)."""
        if self.path.is_file():
            try:
                self.path.unlink()
            except OSError as exc:
                _log.warning(
                    "heartbeat_checkpoint_clear_failed",
                    extra={"path": str(self.path), "error": str(exc)},
                )

    @classmethod
    def default(cls) -> CheckpointWriter:
        return cls(path=default_checkpoint_path())
