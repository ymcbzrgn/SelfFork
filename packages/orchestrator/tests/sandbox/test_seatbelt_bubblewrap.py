"""Sandbox factory + profile generators for seatbelt and bubblewrap backends.

Profile materialisation tests; we don't actually invoke ``sandbox-exec`` or
``bwrap`` here because both are platform-specific and unavailable on CI.
End-to-end exec coverage lives in M5 Order 7 manual smoke + integration
suite.
"""

from __future__ import annotations

import pytest

from selffork_orchestrator.sandbox.bubblewrap_sandbox import (
    BubblewrapSandbox,
    build_bwrap_args,
)
from selffork_orchestrator.sandbox.factory import build_sandbox
from selffork_orchestrator.sandbox.seatbelt_sandbox import (
    SeatbeltSandbox,
    build_sbpl_profile,
)
from selffork_shared.config import SandboxConfig

# ---------------------------------------------------------------------------
# build_sbpl_profile — SBPL string generator
# ---------------------------------------------------------------------------


def test_sbpl_profile_renders_default_fields() -> None:
    profile = build_sbpl_profile(
        workspace="/tmp/ws-1",
        selffork_home="/Users/op/.selffork",
    )
    assert "(version 1)" in profile
    assert "(deny default)" in profile
    assert "/tmp/ws-1" in profile
    assert "/Users/op/.selffork" in profile
    assert "(allow network-outbound" in profile


def test_sbpl_profile_includes_extra_rules() -> None:
    extra = '(allow network-outbound (remote tcp "github.com:443"))'
    profile = build_sbpl_profile(
        workspace="/tmp/ws", selffork_home="/x/.selffork", extra_rules=extra
    )
    assert extra in profile


# ---------------------------------------------------------------------------
# build_bwrap_args — bwrap argv prefix
# ---------------------------------------------------------------------------


def test_bwrap_args_share_net_default() -> None:
    args = build_bwrap_args(workspace="/tmp/ws", selffork_home="/home/op/.selffork")
    assert args[0] == "bwrap"
    assert "--share-net" in args
    assert "--unshare-all" in args
    assert "--die-with-parent" in args
    assert "--bind" in args
    assert "/tmp/ws" in args
    assert "/home/op/.selffork" in args
    assert args[-1] == "--"


def test_bwrap_args_no_share_net() -> None:
    args = build_bwrap_args(
        workspace="/tmp/ws", selffork_home="/home/op/.selffork", share_net=False
    )
    assert "--share-net" not in args


def test_bwrap_args_extra_args_inserted_before_separator() -> None:
    args = build_bwrap_args(
        workspace="/tmp/ws",
        selffork_home="/home/op/.selffork",
        extra_args=["--ro-bind", "/etc", "/etc"],
    )
    sep = args.index("--")
    extras_segment = args[sep - 3 : sep]
    assert extras_segment == ["--ro-bind", "/etc", "/etc"]


# ---------------------------------------------------------------------------
# Sandbox factory dispatch — Order 2 ensures all 4 modes resolve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "expected_cls"),
    [
        ("subprocess", "SubprocessSandbox"),
        ("docker", "DockerSandbox"),
        ("seatbelt", "SeatbeltSandbox"),
        ("bubblewrap", "BubblewrapSandbox"),
    ],
)
def test_factory_dispatch_resolves_all_modes(mode: str, expected_cls: str) -> None:
    config = SandboxConfig(mode=mode)
    sandbox = build_sandbox(config, session_id="s-1")
    assert sandbox.__class__.__name__ == expected_cls


def test_seatbelt_constructor_rejects_wrong_mode() -> None:
    config = SandboxConfig(mode="subprocess")
    with pytest.raises(ValueError, match="seatbelt"):
        SeatbeltSandbox(config, session_id="s-1")


def test_bubblewrap_constructor_rejects_wrong_mode() -> None:
    config = SandboxConfig(mode="subprocess")
    with pytest.raises(ValueError, match="bubblewrap"):
        BubblewrapSandbox(config, session_id="s-1")
