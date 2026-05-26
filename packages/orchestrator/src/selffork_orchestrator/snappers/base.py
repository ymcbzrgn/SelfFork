"""Snapper ABC + filesystem helpers.

The :class:`Snapper` ABC defines the contract concrete per-CLI snappers
implement. The free helpers (:func:`atomic_write_json`, :func:`default_state_dir`,
:func:`snapshot_path`) are shared by every concrete snapper and the
:class:`SnapperRunner` lifecycle.

Atomic write semantics: ``tempfile.mkstemp`` next to the target + ``os.replace`` —
POSIX guarantees concurrent readers never observe partial content. The ``fsync``
between write-and-replace is paranoid but cheap; SnapperRunner runs at 1 Hz, so
the syscall cost is negligible compared to the cost of a torn read corrupting
:class:`UsageAggregator` proactive cache.

Operator-tunable env vars:

* ``SELFFORK_CLI_STATE_DIR`` — override the canonical state directory
  (default ``~/.selffork/cli-state/``). Used by tests to isolate from
  the operator's real on-disk surfaces.
"""
from __future__ import annotations

import contextlib
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel

from selffork_shared.quota import QuotaSnapshot

__all__ = [
    "Snapper",
    "atomic_write_json",
    "default_state_dir",
    "snapshot_path",
]


def default_state_dir() -> Path:
    """Canonical directory for SelfFork CLI state snapshots.

    ``~/.selffork/cli-state/`` — created lazily on first write.

    The ``SELFFORK_CLI_STATE_DIR`` env var overrides the default for
    every consumer (SnapperRunner write side + ProactiveUsageReader
    read side + tooling); set it to a per-test tmp path to keep test
    suites hermetic.
    """
    raw = os.environ.get("SELFFORK_CLI_STATE_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".selffork" / "cli-state"


def snapshot_path(cli_id: str, *, state_dir: Path | None = None) -> Path:
    """Path of the JSON snapshot for ``cli_id``.

    Single per-CLI file (single-account today). If multi-account is added later,
    extend ``cli_id`` to include the account discriminator (e.g. ``codex@user1``);
    consumers only need to learn the new lookup key — file layout unchanged.
    """
    base = state_dir if state_dir is not None else default_state_dir()
    return base / f"{cli_id}.json"


def atomic_write_json(path: Path, payload: BaseModel) -> None:
    """Atomically write a Pydantic model as pretty JSON.

    Pattern:
      1. ``tempfile.mkstemp`` in same directory (so ``os.replace`` is atomic)
      2. write JSON, flush, fsync
      3. ``os.replace`` — single inode swap, readers see either old or new

    Raises:
        OSError: when the temp file cannot be created or replace fails.
            Caller (SnapperRunner) logs and retries; we never write a corrupt file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload.model_dump_json(indent=2))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_path)
        raise


class Snapper(ABC):
    """Abstract base for per-CLI proactive quota snapshot producers.

    Subclasses MUST set ``cli_id`` to match the CLIAgent registry key
    (``opencode`` | ``claude-code`` | ``codex`` | ``gemini-cli`` | ``minimax-cli``).

    The :meth:`snapshot` coroutine returns a fresh :class:`QuotaSnapshot`
    or ``None`` when the signal is not yet available (e.g., the CLI hasn't
    written its first event). Transient signal absence MUST return ``None``;
    only hard errors (corrupted JSONL, denied permission) should raise.

    Subclasses MAY override :meth:`aclose` to release long-lived resources
    (file watcher handles, SSE connections, child processes).
    """

    cli_id: str

    def __init__(self, cli_id: str) -> None:
        self.cli_id = cli_id

    @abstractmethod
    async def snapshot(self) -> QuotaSnapshot | None:
        """Produce one snapshot, or return ``None`` if signal is not yet available."""

    async def aclose(self) -> None:  # noqa: B027 — default no-op is intentional
        """Release any held resources. Default: no-op."""
