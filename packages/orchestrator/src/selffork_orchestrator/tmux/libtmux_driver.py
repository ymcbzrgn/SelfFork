"""LibtmuxDriver — :class:`TmuxDriver` implementation backed by ``libtmux``.

libtmux is a thin Python wrapper around the ``tmux`` binary; we use it
because it handles target-id formatting + send-keys escaping for us
(verified by selffork-researcher 2026-05-01: v0.55.1, actively
maintained, Python >= 3.10).

Async wrapping: libtmux's API is synchronous. We call into it via
``anyio.to_thread.run_sync`` so the rest of SelfFork (asyncio-based)
isn't blocked while tmux operations run.

Nested-tmux note: ``Server()`` connects to the default tmux socket,
which respects ``$TMUX``. If SelfFork is invoked from inside an existing
tmux session (e.g. the user is already in tmux), libtmux would try to
nest. We pop ``TMUX`` from the env we hand to the Server constructor so
the ``run-many`` session lives on the default socket regardless. Per
researcher: this is the documented workaround.

Output capture: libtmux's ``capture_pane()`` is a snapshot of scrollback,
not a stream. For durable per-pane logs we shell out via ``pane.cmd(
"pipe-pane", "-O", f"cat >> {log}")`` — the standard pattern documented
in tmux(1) and confirmed by libtmux's ``cmd()`` escape hatch.

Exit-code detection: tmux has no native exit-code API. The caller is
expected to wrap the user command with a sentinel
(e.g. ``my-cmd; echo "[SELFFORK:EXIT:$?]" >> {log}``) and parse it from
the log file. This driver does not impose a sentinel format — that's a
runner-layer concern.

See: ``packages/orchestrator/src/selffork_orchestrator/tmux/base.py``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import libtmux

from selffork_orchestrator.tmux.base import TmuxDriver
from selffork_shared.errors import TmuxPaneError, TmuxSessionError
from selffork_shared.logging import get_logger

if TYPE_CHECKING:
    from libtmux.pane import Pane
    from libtmux.session import Session

__all__ = ["LibtmuxDriver"]

_log = get_logger(__name__)


class LibtmuxDriver(TmuxDriver):
    """libtmux-backed :class:`TmuxDriver`."""

    def __init__(self) -> None:
        # Strip TMUX so libtmux's Server() doesn't try to nest inside an
        # outer session if the user invoked SelfFork from inside tmux.
        # Mutating os.environ here is intentional and scoped to the
        # process lifetime — multiple drivers in the same process want
        # the same behavior.
        os.environ.pop("TMUX", None)
        self._server = libtmux.Server()
        # Per-session: how many panes WE have added so far. The first
        # add_pane call for a session reuses the session's default pane;
        # subsequent calls split. Tracking this explicitly avoids a
        # timing race where send_keys hasn't yet swapped the default
        # pane's current_command from "zsh" to the user's command, which
        # would fool a heuristic into reusing the same pane twice.
        self._panes_added: dict[str, int] = {}

    async def create_session(self, *, name: str) -> str:
        def _create() -> str:
            try:
                session = self._server.new_session(
                    session_name=name,
                    detach=True,
                    kill_session=False,
                )
            except Exception as exc:  # libtmux raises various subclasses
                raise TmuxSessionError(
                    f"failed to create tmux session {name!r}: {type(exc).__name__}: {exc}",
                ) from exc
            session_id = session.session_name or name
            self._panes_added[session_id] = 0
            _log.info("tmux_session_created", session=session_id)
            return session_id

        return await anyio.to_thread.run_sync(_create)

    async def add_pane(
        self,
        *,
        session_id: str,
        command: str,
        log_path: Path,
    ) -> str:
        def _add() -> str:
            session = self._lookup_session(session_id)
            # ``active_window`` superseded ``attached_window`` in libtmux
            # 0.31.0 (the latter raises DeprecatedError on access in v0.55+).
            window = session.active_window
            if window is None:
                # Fresh session always has a window; if not, something
                # is very wrong.
                raise TmuxPaneError(
                    f"tmux session {session_id!r} has no attached window",
                )
            # First add_pane for this session: reuse the default pane.
            # Subsequent calls always split. Driver state — not pane
            # state — drives this decision (avoids the race described in
            # ``__init__``).
            already_added = self._panes_added.get(session_id, 0)
            if already_added == 0:
                existing_panes = list(window.panes)
                if not existing_panes:
                    raise TmuxPaneError(
                        f"tmux session {session_id!r} has no default pane",
                    )
                pane: Pane = existing_panes[0]
            else:
                try:
                    pane = window.split(attach=False)
                except Exception as exc:
                    raise TmuxPaneError(
                        f"failed to add pane in session {session_id!r}: "
                        f"{type(exc).__name__}: {exc}",
                    ) from exc

            pane_id = pane.pane_id or ""
            if not pane_id:
                raise TmuxPaneError("tmux did not return a pane id after split")

            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.touch(exist_ok=True)

            try:
                # ``-O`` opens for output capture; ``cat >> path``
                # appends so successive panes don't clobber each other.
                # See tmux(1) "pipe-pane -O" and libtmux escape hatch.
                pane.cmd("pipe-pane", "-O", f"cat >> {_shell_quote(log_path)}")
            except Exception as exc:
                raise TmuxPaneError(
                    f"failed to pipe-pane for {pane_id}: {type(exc).__name__}: {exc}",
                ) from exc

            try:
                pane.send_keys(command, enter=True, suppress_history=True)
            except Exception as exc:
                raise TmuxPaneError(
                    f"failed to send command to pane {pane_id}: {type(exc).__name__}: {exc}",
                ) from exc

            self._panes_added[session_id] = already_added + 1
            _log.info(
                "tmux_pane_added",
                session=session_id,
                pane=pane_id,
                log=str(log_path),
                pane_index=already_added,
            )
            return pane_id

        return await anyio.to_thread.run_sync(_add)

    async def is_pane_alive(self, *, pane_id: str) -> bool:
        def _alive() -> bool:
            # ``#{pane_dead}`` is "1" once the pane's process has exited
            # (with ``remain-on-exit on``) or the pane disappears
            # entirely if remain-on-exit is off. We accept either as
            # "not alive": the pane's session may be reaped before we
            # poll. Treat "lookup failed" as dead.
            try:
                # Use the server's cmd to query the pane directly so we
                # don't have to find which window owns it.
                result = self._server.cmd(
                    "display-message",
                    "-p",
                    "-t",
                    pane_id,
                    "#{pane_dead}",
                )
            except Exception:
                return False
            output = result.stdout or []
            if not output:
                return False
            return output[0].strip() == "0"

        return await anyio.to_thread.run_sync(_alive)

    async def kill_session(self, *, session_id: str) -> None:
        def _kill() -> None:
            try:
                self._server.kill_session(session_id)
            except Exception as exc:
                # Idempotent: not-found is fine, log and move on.
                _log.info(
                    "tmux_session_kill_noop",
                    session=session_id,
                    reason=str(exc),
                )
                self._panes_added.pop(session_id, None)
                return
            self._panes_added.pop(session_id, None)
            _log.info("tmux_session_killed", session=session_id)

        await anyio.to_thread.run_sync(_kill)

    # ── internal helpers ──────────────────────────────────────────────

    def _lookup_session(self, session_id: str) -> Session:
        for s in self._server.sessions:
            if s.session_name == session_id or s.session_id == session_id:
                return s
        raise TmuxSessionError(f"tmux session not found: {session_id!r}")


def _shell_quote(path: Path) -> str:
    """Quote a path for safe inclusion in a shell command we hand to tmux.

    The pipe-pane argument is interpreted by ``/bin/sh -c``, so any
    spaces or shell metacharacters in the path would break it.
    """
    s = str(path)
    if not s:
        return "''"
    # Single-quote and escape embedded single quotes via the standard
    # POSIX trick: 'foo'\''bar'.
    return "'" + s.replace("'", "'\\''") + "'"
