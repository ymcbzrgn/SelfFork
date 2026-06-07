"""Tmux desktop driver — M3 snapper-fleet reuse adapter (M5 — ADR-005 §M5-C4).

Body-side adapter that re-exposes the M3 snapper state files + tmux
``send-keys`` / ``capture-pane`` as a body driver. Lets the cockpit Mission
tab and the M5 daemon route uniformly through the body action surface
without bypassing the warden.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

__all__ = ["TmuxDesktopDriver"]

_log = logging.getLogger(__name__)


class TmuxDesktopDriver:
    """Adapter over M3 ``~/.selffork/cli-state/<cli>.json`` snappers + tmux."""

    def __init__(self, *, snapper_root: Path | None = None) -> None:
        self.snapper_root = (snapper_root or Path.home() / ".selffork" / "cli-state").expanduser()

    async def list_sessions(self) -> list[dict[str, Any]]:
        if not self.snapper_root.exists():
            return []
        out: list[dict[str, Any]] = []
        for path in sorted(self.snapper_root.glob("*.json")):
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            payload["cli"] = path.stem
            out.append(payload)
        return out

    async def send_keys(self, target_session: str, target_pane: str, keys: str) -> None:
        """Send ``keys`` to the target tmux pane, splitting on newlines.

        Each line is delivered then followed by an explicit ``C-m`` (Enter).
        Trailing empty lines are dropped. A pure-empty ``keys`` only sends
        ``C-m`` (operator may want to dispatch an empty enter).
        """
        target = f"{target_session}:{target_pane}" if target_pane else target_session
        lines = keys.split("\n")
        # Drop trailing empties so the *last* C-m doesn't duplicate.
        while lines and lines[-1] == "" and len(lines) > 1:
            lines.pop()
        if not lines:
            lines = [""]
        for line in lines:
            args = ["tmux", "send-keys", "-t", target]
            if line:
                args.append(line)
            args.append("C-m")
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"tmux send-keys failed (rc={proc.returncode}): {stderr.decode(errors='replace')}"
                )

    async def capture_pane(self, target_session: str, target_pane: str) -> str:
        target = f"{target_session}:{target_pane}" if target_pane else target_session
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "capture-pane",
            "-p",
            "-t",
            target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"tmux capture-pane failed (rc={proc.returncode}): {stderr.decode(errors='replace')}"
            )
        return stdout.decode(errors="replace")

    # Matches the body driver action surface; the tmux driver is intentionally
    # narrow (CLI control only) so most action methods raise NotImplementedError.

    async def click(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("tmux driver has no pixel surface; use send_keys")

    async def screenshot(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("tmux driver does not capture pixels; use capture_pane")
