"""Tests for :class:`MinimaxCliAgent`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from selffork_orchestrator.cli_agent.minimax_cli import (
    DONE_SENTINEL,
    MinimaxCliAgent,
)
from selffork_shared.config import CLIAgentConfig
from selffork_shared.errors import AgentBinaryNotFoundError


def _make_agent(**overrides: object) -> MinimaxCliAgent:
    cfg = CLIAgentConfig(agent="minimax-cli", **overrides)
    return MinimaxCliAgent(cfg)


def test_init_rejects_wrong_agent() -> None:
    with pytest.raises(ValueError, match="agent='minimax-cli'"):
        MinimaxCliAgent(CLIAgentConfig(agent="opencode"))


def test_resolve_binary_uses_configured_path(tmp_path: Path) -> None:
    fake = tmp_path / "fake-mmx"
    fake.write_text("#!/bin/sh\necho test\n")
    fake.chmod(0o755)
    agent = MinimaxCliAgent(
        CLIAgentConfig(agent="minimax-cli", binary_path=str(fake)),
    )
    assert agent.resolve_binary() == str(fake)


def test_resolve_binary_uses_path_when_present() -> None:
    agent = _make_agent()
    with patch(
        "selffork_orchestrator.cli_agent.minimax_cli.shutil.which",
        return_value="/usr/local/bin/mmx",
    ):
        assert agent.resolve_binary() == "/usr/local/bin/mmx"


def test_resolve_binary_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent()
    monkeypatch.setattr(
        "selffork_orchestrator.cli_agent.minimax_cli._COMMON_INSTALL_PATHS",
        (),
    )
    with (
        patch(
            "selffork_orchestrator.cli_agent.minimax_cli.shutil.which",
            return_value=None,
        ),
        pytest.raises(AgentBinaryNotFoundError, match="mmx auth login"),
    ):
        agent.resolve_binary()


def test_compose_initial_messages_contains_prd_and_workspace() -> None:
    agent = _make_agent()
    msgs = agent.compose_initial_messages(
        prd="add fonksiyonu",
        plan_path="/tmp/plan.md",
        workspace="/tmp/work",
    )
    assert msgs[0]["role"] == "system"
    assert "mmx" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "add fonksiyonu" in msgs[1]["content"]
    assert "/tmp/work" in msgs[1]["content"]


def test_build_command_first_round() -> None:
    agent = _make_agent()
    cmd = agent.build_command(message="hello", is_first_round=True)
    assert cmd == ["chat", "-p", "hello"]


def test_build_command_continuation() -> None:
    agent = _make_agent()
    cmd = agent.build_command(message="hello", is_first_round=False)
    assert cmd == ["chat", "-c", "-p", "hello"]


def test_build_command_includes_extra_args() -> None:
    agent = _make_agent(extra_args=["--region", "global"])
    cmd = agent.build_command(message="hi", is_first_round=True)
    assert cmd == ["chat", "-p", "--region", "global", "hi"]


def test_build_env_disables_color() -> None:
    agent = _make_agent()
    env = agent.build_env({"PATH": "/bin"})
    assert env["TERM"] == "dumb"
    assert env["NO_COLOR"] == "1"


def test_is_done_matches_sentinel() -> None:
    agent = _make_agent()
    assert agent.is_selffork_jr_done(f"All done\n{DONE_SENTINEL}") is True
    assert agent.is_selffork_jr_done("done") is False
