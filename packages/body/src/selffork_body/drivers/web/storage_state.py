"""Per-provider Playwright storage_state persistence (M5 — ADR-005 §M5-E).

Provider OAuth completed flows save here; subsequent ``BrowserContext`` calls
load from the same file to skip re-login. Path policy follows the screenshot
store: ``~/.selffork/projects/<slug>/auth/<provider>.json`` for project-bound
sessions, ``~/.selffork/auth-cache/<provider>.json`` for orphan sessions.

Auto-save watchdog: 30 s default cadence; only writes when a SHA-256 of the
current state differs from the last write (no spurious writes on every tick).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["StorageStateAutoSave", "WebStorageStateManager"]

_log = logging.getLogger(__name__)


class WebStorageStateManager:
    """Disk-backed manager for Playwright ``storage_state`` JSON files."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = (root or Path.home() / ".selffork").expanduser()

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, provider: str, project_slug: str | None = None) -> Path:
        if not provider:
            raise ValueError("provider must be non-empty")
        if project_slug:
            return self._root / "projects" / project_slug / "auth" / f"{provider}.json"
        return self._root / "auth-cache" / f"{provider}.json"

    async def save(
        self,
        context: Any,
        provider: str,
        project_slug: str | None = None,
    ) -> Path:
        state = await context.storage_state()
        path = self.path_for(provider, project_slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        # M5 audit-fix wave — tighten file mode: storage_state JSON holds
        # session cookies + provider tokens; 0o600 keeps it owner-only on
        # multi-user hosts.
        try:
            path.chmod(0o600)
        except OSError:  # pragma: no cover - filesystem may not support chmod
            pass
        return path

    def load_path(self, provider: str, project_slug: str | None = None) -> Path | None:
        path = self.path_for(provider, project_slug)
        return path if path.exists() else None

    def delete(self, provider: str, project_slug: str | None = None) -> bool:
        path = self.path_for(provider, project_slug)
        if not path.exists():
            return False
        path.unlink()
        return True


@dataclass
class StorageStateAutoSave:
    """Background task that re-saves the context's ``storage_state`` on change."""

    manager: WebStorageStateManager
    context: object  # Playwright BrowserContext at runtime
    provider: str
    project_slug: str | None = None
    interval_sec: float = 30.0
    _task: asyncio.Task[None] | None = field(default=None, init=False)
    _last_hash: str = field(default="", init=False)
    _stop: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    async def _digest(self) -> str:
        state = await self.context.storage_state()  # type: ignore[attr-defined]
        canon = json.dumps(state, sort_keys=True).encode("utf-8")
        return hashlib.sha256(canon).hexdigest()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                digest = await self._digest()
            except Exception:
                break
            if digest != self._last_hash:
                try:
                    await self.manager.save(self.context, self.provider, self.project_slug)
                    self._last_hash = digest
                except Exception as exc:
                    _log.warning(
                        "storage_state_autosave_failed provider=%s err=%s", self.provider, exc
                    )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_sec)
            except TimeoutError:
                continue

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self._loop(), name=f"storage_state_autosave:{self.provider}"
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
