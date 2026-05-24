"""Affinity-landscape snapshot — Self Jr's cross-process read bridge (S6).

Self Jr's round-loop runs in a ``selffork run`` subprocess that cannot
open the affinity DuckDB (the dashboard owns it single-writer; see
:mod:`selffork_orchestrator.router.outcomes`). So the dashboard persists
each workspace's computed affinity landscape (a
:meth:`~selffork_orchestrator.router.affinity.CliSelection.to_metadata`
dict) to a small JSON file when it routes that workspace; Self Jr's
``cli_affinity`` tool reads it. Same file hand-off shape as the
quota-snapshot files + the outcomes JSONL: the dashboard is the sole
writer, the subprocess only reads.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "affinity_snapshot_dir",
    "affinity_snapshot_path",
    "read_affinity_snapshot",
    "write_affinity_snapshot",
]

# Filename-safe slug (mirrors dashboard.heartbeat_wire); collapses the rest to "-".
_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def affinity_snapshot_dir(*, home: Path | None = None) -> Path:
    """``~/.selffork/router/affinity_snapshot`` — shared cross-process."""
    base = home if home is not None else Path("~/.selffork").expanduser()
    return base / "router" / "affinity_snapshot"


def affinity_snapshot_path(workspace: str, *, home: Path | None = None) -> Path:
    """Per-workspace snapshot file path."""
    safe = _SLUG_RE.sub("-", workspace) or "_"
    return affinity_snapshot_dir(home=home) / f"{safe}.json"


def write_affinity_snapshot(
    workspace: str,
    metadata: dict[str, object],
    *,
    home: Path | None = None,
) -> None:
    """Atomically persist one workspace's affinity landscape (dashboard side).

    ``metadata`` is a :meth:`CliSelection.to_metadata` dict (chosen
    cli/model, scores, match_levels, eligible, quota_filtered). Written via
    temp-file + ``os.replace`` so a concurrent reader never sees a torn
    file.
    """
    path = affinity_snapshot_path(workspace, home=home)
    path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, object] = {
        "workspace": workspace,
        "recorded_at": datetime.now(tz=UTC).isoformat(),
        **metadata,
    }
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(record, fp)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def read_affinity_snapshot(
    workspace: str,
    *,
    home: Path | None = None,
) -> dict[str, Any] | None:
    """Read one workspace's affinity landscape (subprocess/tool side).

    Returns ``None`` when no snapshot exists yet or the file is unreadable
    / malformed — the caller degrades gracefully.
    """
    path = affinity_snapshot_path(workspace, home=home)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
