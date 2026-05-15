"""Tests for :class:`CodexAgent`."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from selffork_orchestrator.cli_agent.codex import DONE_SENTINEL, CodexAgent
from selffork_shared.config import CLIAgentConfig
from selffork_shared.errors import AgentBinaryNotFoundError


def _make_agent(**overrides: object) -> CodexAgent:
    cfg = CLIAgentConfig(agent="codex", **overrides)
    return CodexAgent(cfg)


def test_init_rejects_wrong_agent() -> None:
    with pytest.raises(ValueError, match="agent='codex'"):
        CodexAgent(CLIAgentConfig(agent="opencode"))


def test_resolve_binary_uses_configured_path(tmp_path: Path) -> None:
    fake = tmp_path / "fake-codex"
    fake.write_text("#!/bin/sh\necho test\n")
    fake.chmod(0o755)
    agent = CodexAgent(CLIAgentConfig(agent="codex", binary_path=str(fake)))
    assert agent.resolve_binary() == str(fake)


def test_resolve_binary_rejects_non_executable_configured_path(tmp_path: Path) -> None:
    fake = tmp_path / "not-executable"
    fake.write_text("hello")
    agent = CodexAgent(CLIAgentConfig(agent="codex", binary_path=str(fake)))
    with pytest.raises(AgentBinaryNotFoundError):
        agent.resolve_binary()


def test_resolve_binary_uses_path_when_present() -> None:
    agent = _make_agent()
    with patch(
        "selffork_orchestrator.cli_agent.codex.shutil.which",
        return_value="/usr/local/bin/codex",
    ):
        assert agent.resolve_binary() == "/usr/local/bin/codex"


def test_resolve_binary_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent()
    monkeypatch.setattr(
        "selffork_orchestrator.cli_agent.codex._COMMON_INSTALL_PATHS",
        (),
    )
    with patch(
        "selffork_orchestrator.cli_agent.codex.shutil.which",
        return_value=None,
    ), pytest.raises(AgentBinaryNotFoundError, match="codex login"):
        agent.resolve_binary()


def test_compose_initial_messages_contains_prd_and_workspace() -> None:
    agent = _make_agent()
    msgs = agent.compose_initial_messages(
        prd="add fonksiyonu yaz",
        plan_path="/tmp/plan.md",
        workspace="/tmp/work",
    )
    assert msgs[0]["role"] == "system"
    assert "codex" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "add fonksiyonu yaz" in msgs[1]["content"]
    assert "/tmp/work" in msgs[1]["content"]
    assert "/tmp/plan.md" in msgs[1]["content"]


_AUTO_APPROVE = (
    "--skip-git-repo-check",
    "--dangerously-bypass-approvals-and-sandbox",
)


def test_build_command_first_round() -> None:
    agent = _make_agent()
    cmd = agent.build_command(message="hello", is_first_round=True)
    assert cmd == ["exec", *_AUTO_APPROVE, "hello"]


def test_build_command_continuation() -> None:
    agent = _make_agent()
    cmd = agent.build_command(message="hello", is_first_round=False)
    assert cmd == ["exec", *_AUTO_APPROVE, "--resume-last", "hello"]


def test_build_command_includes_extra_args() -> None:
    agent = _make_agent(extra_args=["--profile", "fast"])
    cmd = agent.build_command(message="hi", is_first_round=True)
    assert cmd == ["exec", *_AUTO_APPROVE, "--profile", "fast", "hi"]


def test_build_command_extra_args_with_continuation() -> None:
    agent = _make_agent(extra_args=["--profile", "fast"])
    cmd = agent.build_command(message="hi", is_first_round=False)
    assert cmd == [
        "exec",
        *_AUTO_APPROVE,
        "--resume-last",
        "--profile",
        "fast",
        "hi",
    ]


def test_build_env_disables_color() -> None:
    agent = _make_agent()
    env = agent.build_env({"PATH": "/bin"})
    assert env["TERM"] == "dumb"
    assert env["NO_COLOR"] == "1"
    assert env["PATH"] == "/bin"


def test_build_env_preserves_user_overrides() -> None:
    agent = _make_agent()
    env = agent.build_env({"PATH": "/bin", "TERM": "xterm-256color"})
    # build_env uses setdefault — caller's TERM stays.
    assert env["TERM"] == "xterm-256color"


def test_is_done_matches_sentinel() -> None:
    agent = _make_agent()
    assert agent.is_selffork_jr_done(f"All done\n{DONE_SENTINEL}") is True
    assert agent.is_selffork_jr_done("tamam, devam edelim") is False
    # 'done' alone is not the literal sentinel.
    assert agent.is_selffork_jr_done("done") is False
