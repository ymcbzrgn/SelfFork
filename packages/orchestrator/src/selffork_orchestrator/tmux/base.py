"""TmuxDriver ABC — adapter contract for spawning + monitoring tmux panes.

SelfFork's ``run-many`` command needs to drive N tmux panes in parallel
(each pane = one independent ``selffork run`` invocation against a
shared MLX runtime). Tmux gives us cheap process multiplexing, easy
detachable UX (``tmux attach``), and per-pane lifecycle isolation.

The driver is intentionally **stateless** — IDs (session_id, pane_id)
are threaded through so a single driver instance can manage multiple
sessions concurrently if needed. Per-session state lives in tmux itself.

The default implementation is :class:`LibtmuxDriver` (in
``libtmux_driver.py``); the Protocol exists so a future
``SubprocessTmuxDriver`` (or a no-libtmux fallback) can drop in without
touching the call sites.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §17 (planned tmux extension)
and ``feedback_infra_before_finetune.md`` (infra-first sequencing).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

__all__ = ["TmuxDriver"]


class TmuxDriver(ABC):
    """Adapter for spawning and managing tmux sessions + panes."""

    @abstractmethod
    async def create_session(self, *, name: str) -> str:
        """Create a fresh detached tmux session.

        Returns:
            The session id (typically equal to ``name``, but the driver
            may normalize it — callers should treat the return value as
            opaque).

        Raises:
            selffork_shared.errors.TmuxSessionError: if the session can't
                be created (e.g., name already exists, tmux missing).
        """

    @abstractmethod
    async def add_pane(
        self,
        *,
        session_id: str,
        command: str,
        log_path: Path,
    ) -> str:
        """Add a pane to ``session_id``, run ``command`` in it, pipe its
        stdout/stderr to ``log_path`` via ``tmux pipe-pane``.

        For the FIRST pane in a fresh session, the driver may use the
        session's default window/pane rather than splitting — the caller
        should not assume splits happen N times for N panes.

        Args:
            session_id: from :meth:`create_session`.
            command: shell command to execute in the new pane. The
                driver passes this through to tmux ``send-keys`` —
                callers are responsible for shell-escaping arguments.
            log_path: file path to which the pane's combined output
                should be appended via ``tmux pipe-pane``. Created if
                it doesn't exist.

        Returns:
            The pane id (e.g. ``%17``).

        Raises:
            selffork_shared.errors.TmuxPaneError: if the pane can't be
                created or piping fails.
        """

    @abstractmethod
    async def is_pane_alive(self, *, pane_id: str) -> bool:
        """Return ``True`` while the pane process is still running.

        Implementations typically query ``#{pane_dead}`` via
        ``tmux display-message`` or check whether the pane id is still
        listed by ``tmux list-panes``.
        """

    @abstractmethod
    async def kill_session(self, *, session_id: str) -> None:
        """Tear down the session. Idempotent — must not raise if the
        session is already gone.
        """
