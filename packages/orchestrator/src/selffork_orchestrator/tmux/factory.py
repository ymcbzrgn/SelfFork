"""Backend → implementation resolver for :class:`TmuxDriver`.

Today only one backend (``libtmux``) is implemented; the factory exists
so future drivers (subprocess fallback, alternate libraries) can drop in
without touching call sites.
"""

from __future__ import annotations

from selffork_orchestrator.tmux.base import TmuxDriver
from selffork_orchestrator.tmux.libtmux_driver import LibtmuxDriver

__all__ = ["build_tmux_driver"]


def build_tmux_driver() -> TmuxDriver:
    """Return a fresh :class:`TmuxDriver` instance.

    Currently always returns :class:`LibtmuxDriver`. When a second
    backend lands, this function gains a config arg and dispatches by
    name (mirroring :func:`build_cli_agent`).
    """
    return LibtmuxDriver()
