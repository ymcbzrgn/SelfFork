"""Unit tests for :mod:`selffork_shared.ports`."""

from __future__ import annotations

import socket
from contextlib import closing

from selffork_shared.ports import find_free_port, is_port_free


def test_find_free_port_returns_valid_range() -> None:
    port = find_free_port()
    assert 1 <= port <= 65535


def test_find_free_port_yields_actually_free_port() -> None:
    port = find_free_port()
    assert is_port_free(port) is True


def test_is_port_free_returns_false_for_taken_port() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        taken = sock.getsockname()[1]
        assert is_port_free(taken) is False
    finally:
        sock.close()


def test_find_free_port_consecutive_calls_return_valid_ports() -> None:
    # Not guaranteed unique (kernel may reuse), but each must be a valid
    # local TCP port.
    for _ in range(5):
        port = find_free_port()
        assert 1 <= port <= 65535


def test_is_port_free_with_explicit_host() -> None:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # Now released; should be free again
    assert is_port_free(port, host="127.0.0.1") is True
