"""TmuxSpawnRunner — :class:`SpawnHandler` impl that spawns children via tmux.

When the parent's Jr emits ``[SELFFORK:SPAWN: <spec>]``, this runner:

1. For each request, writes the spec to a temp PRD file under
   ``~/.selffork/spawned/<parent_session_id>/spec-<i>.md``.
2. Builds a ``selffork run`` command per child with environment vars
   pinning the child to **shared-mode runtime** at the parent's MLX
   port (so all panes hit the same warm model).
3. Creates a fresh tmux session, splits N panes, runs each child.
4. Polls every ``poll_interval_seconds`` until ALL panes are dead.
5. Reads each pane's log, extracts the per-child exit code via the
   ``[SELFFORK:EXIT:<n>]`` sentinel pattern (same shape as
   ``selffork run-many`` Faz 0), and aggregates the outputs.
6. Returns one user-role string the parent's next round can read.

Aggregator format: a delimited block per child with the spec, exit
code, and the last ~120 lines of pane output. We trim because pane
logs include shell escape sequences and we want the parent Jr to read
human-readable text.
"""

from __future__ import annotations

import asyncio
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from selffork_orchestrator.spawn.sentinel import SpawnRequest
from selffork_orchestrator.tmux.base import TmuxDriver
from selffork_shared.logging import get_logger

__all__ = ["SpawnRunnerConfig", "TmuxSpawnRunner"]

_log = get_logger(__name__)

# Pattern shared with ``selffork run-many``: every child appends
# ``[SELFFORK:EXIT:<code>]`` to its pane log so the parent can recover
# the exit code (tmux has no native exit-code API).
_EXIT_RE = re.compile(r"\[SELFFORK:EXIT:(-?\d+)\]")

# Number of trailing log lines included in the aggregated output. Tmux
# panes contain shell prompts + ANSI escapes + the actual selffork run
# stdout — keeping the tail capped lets Jr read something useful.
_TAIL_LINES = 120


@dataclass(frozen=True, slots=True)
class SpawnRunnerConfig:
    """Inputs the runner needs to spawn child processes.

    Attributes:
        selffork_script: absolute path to the ``selffork`` console script
            (typically ``<venv>/bin/selffork``).
        config_path: parent's ``--config`` arg, passed through to children
            so they share the same selffork.yaml. ``None`` ⇒ children
            use the default selffork.yaml resolution.
        shared_host: parent runtime host (e.g. ``127.0.0.1``).
        shared_port: parent runtime port (children attach in shared mode).
        log_root: directory where each child pane's log is written
            (one file per pane). Created if missing.
        poll_interval_seconds: how often to scan for dead panes. Default 2s.
    """

    selffork_script: Path
    config_path: Path | None
    shared_host: str
    shared_port: int
    log_root: Path
    poll_interval_seconds: float = 2.0


class TmuxSpawnRunner:
    """Spawn children via tmux + shared MLX, aggregate their outputs."""

    def __init__(self, *, tmux: TmuxDriver, config: SpawnRunnerConfig) -> None:
        self._tmux = tmux
        self._config = config

    async def __call__(
        self,
        *,
        parent_session_id: str,
        requests: list[SpawnRequest],
    ) -> str:
        """Spawn each request as a child pane, wait for all, aggregate."""
        spawn_root = self._config.log_root / parent_session_id
        spawn_root.mkdir(parents=True, exist_ok=True)

        # tmux session names are filesystem-friendly — keep short.
        tmux_session = f"selffork-spawn-{parent_session_id[-12:].lower()}"
        await self._tmux.create_session(name=tmux_session)

        panes: list[_PaneRecord] = []
        try:
            for req in requests:
                prd_path = spawn_root / f"spec-{req.index:02d}.md"
                prd_path.write_text(
                    f"# Auto-generated PRD from SELFFORK:SPAWN\n\n{req.spec}\n",
                    encoding="utf-8",
                )
                pane_log = spawn_root / f"pane-{req.index:02d}.log"
                cmd = self._build_child_command(prd_path)
                pane_id = await self._tmux.add_pane(
                    session_id=tmux_session,
                    command=cmd,
                    log_path=pane_log,
                )
                panes.append(
                    _PaneRecord(
                        request=req,
                        pane_id=pane_id,
                        log_path=pane_log,
                        prd_path=prd_path,
                    ),
                )
                _log.info(
                    "spawn_pane_added",
                    parent=parent_session_id,
                    pane=pane_id,
                    spec_preview=req.spec[:80],
                )

            # Poll until every pane is dead.
            while True:
                alive = [p for p in panes if await self._tmux.is_pane_alive(pane_id=p.pane_id)]
                if not alive:
                    break
                _log.info(
                    "spawn_poll",
                    parent=parent_session_id,
                    alive_count=len(alive),
                )
                await asyncio.sleep(self._config.poll_interval_seconds)

            return _aggregate(panes)
        finally:
            await self._tmux.kill_session(session_id=tmux_session)

    def _build_child_command(self, prd: Path) -> str:
        """Shell command for one pane. Mirrors run-many's child shape.

        Inline env vars switch the child runtime to shared mode so it
        reuses the parent's already-warm MLX server. The trailing
        ``echo "[SELFFORK:EXIT:$?]"`` makes pane exit-codes recoverable
        from the log.
        """
        parts: list[str] = [
            "SELFFORK_RUNTIME__MODE=shared",
            f"SELFFORK_RUNTIME__PORT={self._config.shared_port}",
            f"SELFFORK_RUNTIME__HOST={shlex.quote(self._config.shared_host)}",
            shlex.quote(str(self._config.selffork_script)),
            "run",
            shlex.quote(str(prd)),
        ]
        if self._config.config_path is not None:
            parts.extend(["--config", shlex.quote(str(self._config.config_path))])
        base = " ".join(parts)
        return f'{base}; echo "[SELFFORK:EXIT:$?]"'


@dataclass(frozen=True, slots=True)
class _PaneRecord:
    request: SpawnRequest
    pane_id: str
    log_path: Path
    prd_path: Path


def _aggregate(panes: list[_PaneRecord]) -> str:
    """Build the user-role text the parent Jr will see for this round.

    Format intentionally human-readable so future fine-tunes can train
    on it as part of the round-loop corpus (see
    ``feedback_infra_before_finetune.md``).
    """
    blocks: list[str] = ["=== Spawned children completed ==="]
    for p in panes:
        text = ""
        if p.log_path.is_file():
            text = p.log_path.read_text(encoding="utf-8", errors="replace")
        exit_code = _parse_exit(text)
        status = "OK" if exit_code == 0 else f"FAILED (exit {exit_code})"
        tail = _tail_lines(text, _TAIL_LINES)
        blocks.append(
            f"--- Child {p.request.index}: {status} ---\nSpec: {p.request.spec}\nOutput:\n{tail}",
        )
    blocks.append("=== /Spawned ===")
    blocks.append("[Now decide the next step.]")
    return "\n\n".join(blocks)


def _parse_exit(text: str) -> int | None:
    matches = _EXIT_RE.findall(text)
    return int(matches[-1]) if matches else None


def _tail_lines(text: str, n: int) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:])
