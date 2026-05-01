"""Tests for :func:`build_tmux_driver`."""

from __future__ import annotations

from selffork_orchestrator.tmux.factory import build_tmux_driver
from selffork_orchestrator.tmux.libtmux_driver import LibtmuxDriver


def test_factory_returns_libtmux_driver() -> None:
    driver = build_tmux_driver()
    assert isinstance(driver, LibtmuxDriver)


def test_factory_returns_fresh_instance_each_call() -> None:
    a = build_tmux_driver()
    b = build_tmux_driver()
    assert a is not b
