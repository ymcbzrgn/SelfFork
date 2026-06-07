"""Session-outcome feedback channel — ADR-006 §4.6 affinity write-path (S6).

A ``selffork run`` session ends inside a **subprocess** (spawned by the
dashboard or the operator). The affinity DuckDB store is owned by the
**dashboard** process; DuckDB is single-writer per file, so the
subprocess must not open it. Instead the subprocess appends one
:class:`SessionOutcome` line to a JSONL log (POSIX ``O_APPEND`` makes
short single-line writes atomic across processes), and the dashboard
drains the log into the affinity store before each read
(:class:`~selffork_orchestrator.router.affinity.CliAffinityProvider.drain`).

A persisted byte-offset checkpoint makes the drain idempotent across
dashboard restarts (the same tail-follow shape S-Memory's heartbeat
ingester uses). This mirrors the ADR-009 "structured-source bypass"
ingest philosophy: the writer emits a durable record; the owner folds it
in on its own schedule.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "OutcomeIngester",
    "SessionOutcome",
    "append_session_outcome",
    "default_outcome_log_path",
]

_log = logging.getLogger(__name__)


class SessionOutcome(BaseModel):
    """One finished session's affinity signal (turn-to-complete metric)."""

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    workspace_slug: str
    cli: str
    model: str
    succeeded: bool
    turns: int = Field(ge=0)
    task_type: str | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


def default_outcome_log_path() -> Path:
    """``~/.selffork/router/outcomes.jsonl`` — shared cross-process log."""
    return Path("~/.selffork/router/outcomes.jsonl").expanduser()


def append_session_outcome(path: Path, outcome: SessionOutcome) -> None:
    """Atomically append one outcome line (subprocess side).

    A single ``write`` of a sub-PIPE_BUF line under ``O_APPEND`` is
    atomic on POSIX, so concurrent ``selffork run`` processes never
    interleave lines.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = outcome.model_dump_json() + "\n"
    with path.open("a", encoding="utf-8") as fp:
        fp.write(line)


class OutcomeIngester:
    """Drains new :class:`SessionOutcome` lines via a byte-offset checkpoint.

    Owned by the dashboard process (the sole affinity-store writer). The
    checkpoint file (``<log>.offset``) records how far the log has been
    consumed so a restart never re-ingests — affinity counts stay honest.
    """

    def __init__(self, *, log_path: Path) -> None:
        self._log_path = log_path
        self._offset_path = log_path.with_name(log_path.name + ".offset")

    def _read_offset(self) -> int:
        try:
            return int(self._offset_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return 0

    def _write_offset(self, offset: int) -> None:
        self._offset_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._offset_path.with_suffix(self._offset_path.suffix + ".tmp")
        tmp.write_text(str(offset), encoding="utf-8")
        tmp.replace(self._offset_path)

    async def drain(self, handler: Callable[[SessionOutcome], Awaitable[None]]) -> int:
        """Fold every new complete line into ``handler``; return the count.

        Only newline-terminated lines are consumed (a partial trailing
        line — a writer mid-append — is left for the next drain).
        """
        if not self._log_path.is_file():
            return 0
        offset = self._read_offset()
        size = self._log_path.stat().st_size
        if offset > size:
            # Log was truncated/rotated under us — restart from the top.
            offset = 0
        consumed = offset
        count = 0
        with self._log_path.open("r", encoding="utf-8") as fp:
            fp.seek(offset)
            for line in fp:
                if not line.endswith("\n"):
                    break  # partial line — wait for the writer to finish
                consumed += len(line.encode("utf-8"))
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    outcome = SessionOutcome.model_validate_json(stripped)
                except ValueError:
                    _log.warning(
                        "session_outcome_malformed_line",
                        extra={"path": str(self._log_path)},
                    )
                    continue
                await handler(outcome)
                count += 1
        if consumed != offset:
            self._write_offset(consumed)
        return count
