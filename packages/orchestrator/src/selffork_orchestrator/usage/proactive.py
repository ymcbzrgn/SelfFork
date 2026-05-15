"""Proactive usage layer — read per-CLI :class:`QuotaSnapshot` files.

Companion to the audit-log-derived :class:`UsageAggregator`: when proactive
snappers are running and producing ``~/.selffork/cli-state/<cli>.json``, this
layer reads those files for low-latency, high-fidelity quota state.

Stale snapshots (older than ``stale_after_seconds``) are filtered; callers
fall back to the audit-log derivation layer when proactive is absent. Both
layers coexist by design — see ``project_provider_usage_source.md``.

This module provides a thin reader; it does NOT manage snapper lifecycle
(see :class:`selffork_orchestrator.snappers.runner.SnapperRunner`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from selffork_orchestrator.snappers.base import default_state_dir, snapshot_path
from selffork_shared.quota import QuotaSnapshot

__all__ = ["ProactiveUsageReader", "ProactiveUsageReaderConfig"]


@dataclass(frozen=True, slots=True)
class ProactiveUsageReaderConfig:
    """Reader config.

    Attributes:
        state_dir: Override; defaults to ``~/.selffork/cli-state/``.
        stale_after_seconds: Snapshots older than this are filtered out
            of :meth:`ProactiveUsageReader.read` results. Default 5 min —
            generous because some snappers (e.g. opencode SQLite) only
            update on assistant turns, which can be sparse.
    """

    state_dir: Path | None = None
    stale_after_seconds: float = 300.0


class ProactiveUsageReader:
    """Read per-CLI :class:`QuotaSnapshot` files written by SnapperRunner.

    Stateless and cheap to construct. Designed to be called per Jr autopilot
    ``quota_snapshot()`` tool invocation or per dashboard refresh tick.
    """

    def __init__(self, config: ProactiveUsageReaderConfig | None = None) -> None:
        self._config = config if config is not None else ProactiveUsageReaderConfig()

    @property
    def state_dir(self) -> Path:
        return self._config.state_dir or default_state_dir()

    def read(self, cli_id: str) -> QuotaSnapshot | None:
        """Read and validate the latest snapshot for ``cli_id``.

        Returns ``None`` when:
          - The file does not exist (snapper not running or never produced).
          - The file content is malformed JSON (no raise; treated as absent).
          - The validated snapshot is older than ``stale_after_seconds``.
        """
        path = snapshot_path(cli_id, state_dir=self._config.state_dir)
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        # ``model_validate_json`` parses datetime / enum keys correctly in strict
        # mode, where ``model_validate`` would reject them as un-coerced strings.
        try:
            snap = QuotaSnapshot.model_validate_json(text)
        except ValidationError:
            return None
        if snap.age_seconds() > self._config.stale_after_seconds:
            return None
        return snap

    def read_all(self) -> dict[str, QuotaSnapshot]:
        """Read snapshots for every CLI present in the state dir.

        Skips dotfiles and any snapshot that fails the freshness gate.
        Returns a dict keyed by ``cli_id``.
        """
        result: dict[str, QuotaSnapshot] = {}
        state_dir = self.state_dir
        if not state_dir.is_dir():
            return result
        for path in state_dir.glob("*.json"):
            if path.name.startswith("."):
                continue
            cli_id = path.stem
            snap = self.read(cli_id)
            if snap is not None:
                result[cli_id] = snap
        return result
