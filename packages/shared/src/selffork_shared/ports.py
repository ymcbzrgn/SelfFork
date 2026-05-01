"""Free-port allocation for local services (LLM runtime, opencode HTTP, etc.).

Pattern: bind a socket to port 0, let the kernel pick a free port, close,
return the number. Inspired by the port-probe in
`prior art in the agentic-CLI orchestration space`.

Race-prone in theory — between close() and the consumer's bind(), another
process could grab the port. Acceptable for local dev (sub-second window);
the consumer must handle EADDRINUSE and retry if it loses the race.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §13.
"""

from __future__ import annotations

import socket
from contextlib import closing

__all__ = ["find_free_port", "is_port_free"]


def find_free_port(host: str = "127.0.0.1") -> int:
    """Return a port that's free on ``host`` right now.

    The kernel guarantees the port is free at the instant of return; the
    consumer must bind quickly to minimise the race window.
    """
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, 0))
        port: int = sock.getsockname()[1]
        return port


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """Cheap probe: return True if ``(host, port)`` accepts a fresh bind."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
        return True
