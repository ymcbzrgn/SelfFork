"""FilesystemPlanStore — JSON file under the workspace directory.

Writes the plan to ``<workspace_path>/<plan_filename>``. ``save`` is atomic
via temp-file-then-rename (``os.replace``) so a partially-written plan
never becomes visible to readers (the agent reads this file mid-session).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from selffork_orchestrator.plan.model import Plan, SubTaskState
from selffork_orchestrator.plan.store_base import PlanStore
from selffork_shared.config import PlanConfig
from selffork_shared.errors import PlanLoadError, PlanSaveError
from selffork_shared.logging import get_logger

__all__ = ["FilesystemPlanStore"]

_log = get_logger(__name__)


class FilesystemPlanStore(PlanStore):
    """JSON-on-disk plan store. See module docstring for atomicity guarantees."""

    def __init__(self, config: PlanConfig, workspace_path: str) -> None:
        if config.backend != "filesystem":
            raise ValueError(
                f"FilesystemPlanStore requires backend='filesystem', got {config.backend!r}",
            )
        self._config = config
        self._workspace_path = Path(workspace_path)

    @property
    def plan_path(self) -> Path:
        """Absolute path to the plan JSON file on disk."""
        return self._workspace_path / self._config.plan_filename

    async def load(self) -> Plan:
        path = self.plan_path
        try:
            raw = await asyncio.to_thread(_read_text, path)
        except FileNotFoundError as exc:
            raise PlanLoadError(f"plan file not found: {path}") from exc
        except OSError as exc:
            raise PlanLoadError(f"failed to read plan file {path}: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PlanLoadError(f"plan file is not valid JSON ({path}): {exc}") from exc
        try:
            return Plan.model_validate(data)
        except ValidationError as exc:
            raise PlanLoadError(
                f"plan file failed schema validation ({path}): {exc}",
            ) from exc

    async def save(self, plan: Plan) -> None:
        path = self.plan_path
        try:
            await asyncio.to_thread(_atomic_write_json, path, plan.model_dump(mode="json"))
        except OSError as exc:
            raise PlanSaveError(f"failed to save plan to {path}: {exc}") from exc
        _log.info("plan_saved", path=str(path), subtask_count=len(plan.subtasks))

    async def update_subtask_state(
        self,
        subtask_id: str,
        new_state: SubTaskState,
        notes: str | None = None,
    ) -> Plan:
        plan = await self.load()
        target = plan.find_subtask(subtask_id)
        if target is None:
            raise PlanLoadError(f"subtask not in plan: {subtask_id}")
        target.state = new_state
        if notes is not None:
            target.notes = notes
        now = datetime.now(UTC)
        target.updated_at = now
        plan.updated_at = now
        await self.save(plan)
        return plan


def _read_text(path: Path) -> str:
    """Sync helper for ``asyncio.to_thread``."""
    return path.read_text(encoding="utf-8")


def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
    """Write ``data`` as pretty-printed JSON to ``path`` atomically.

    Uses a same-directory temp file + ``os.replace`` so the rename is
    atomic on POSIX (and atomic-enough on Windows, though we don't target
    Windows in MVP).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".plan.",
        suffix=".json.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=2, sort_keys=True, ensure_ascii=False)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        # Best-effort cleanup of the temp file on any failure path.
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
