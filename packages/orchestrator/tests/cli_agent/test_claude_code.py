"""Unit tests for :class:`ClaudeCodeAgent` (round-loop architecture)."""

from __future__ import annotations

from pathlib import Path

import pytest

from selffork_orchestrator.cli_agent.claude_code import (
    DONE_SENTINEL,
    ClaudeCodeAgent,
)
from selffork_shared.config import CLIAgentConfig
from selffork_shared.errors import AgentBinaryNotFoundError


def _make_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


class TestInit:
    def test_validates_agent_field(self) -> None:
        cfg = CLIAgentConfig(agent="opencode")
        with pytest.raises(ValueError, match="claude-code"):
            ClaudeCodeAgent(cfg)


class TestResolveBinary:
    def test_explicit_path_when_executable(self, tmp_path: Path) -> None:
        fake = tmp_path / "claude-fake"
        _make_executable(fake)
        cfg = CLIAgentConfig(agent="claude-code", binary_path=str(fake))
        agent = ClaudeCodeAgent(cfg)
        assert agent.resolve_binary() == str(fake)

    def test_explicit_path_missing_raises(self, tmp_path: Path) -> None:
        cfg = CLIAgentConfig(
            agent="claude-code",
            binary_path=str(tmp_path / "no-such-binary"),
        )
        agent = ClaudeCodeAgent(cfg)
        with pytest.raises(AgentBinaryNotFoundError, match="not an executable"):
            agent.resolve_binary()

    def test_explicit_path_not_executable_raises(self, tmp_path: Path) -> None:
        fake = tmp_path / "claude-non-exec"
        fake.write_text("not executable", encoding="utf-8")
        cfg = CLIAgentConfig(agent="claude-code", binary_path=str(fake))
        agent = ClaudeCodeAgent(cfg)
        with pytest.raises(AgentBinaryNotFoundError):
            agent.resolve_binary()

    def test_falls_back_to_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_dir = tmp_path / "bin"
        fake_dir.mkdir()
        fake = fake_dir / "claude"
        _make_executable(fake)
        monkeypatch.setenv("PATH", str(fake_dir))
        cfg = CLIAgentConfig(agent="claude-code")
        agent = ClaudeCodeAgent(cfg)
        assert agent.resolve_binary() == str(fake)

    def test_not_found_raises_with_hint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PATH", str(tmp_path / "no-such"))
        monkeypatch.setattr(
            "selffork_orchestrator.cli_agent.claude_code._COMMON_INSTALL_PATHS",
            (tmp_path / "fake1", tmp_path / "fake2"),
        )
        cfg = CLIAgentConfig(agent="claude-code")
        agent = ClaudeCodeAgent(cfg)
        with pytest.raises(AgentBinaryNotFoundError, match="install"):
            agent.resolve_binary()


class TestComposeInitialMessages:
    def test_returns_system_then_user(self) -> None:
        cfg = CLIAgentConfig(agent="claude-code")
        agent = ClaudeCodeAgent(cfg)
        msgs = agent.compose_initial_messages(
            prd="Build hello.py",
            plan_path=".selffork/plan.json",
            workspace="/var/data/sandbox/ws",
        )
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert "SelfFork Jr" in msgs[0]["content"]
        # System prompt names the CLI being driven so SelfFork Jr can address
        # it correctly. claude-code is "claude" in the prompt body.
        assert "claude" in msgs[0]["content"]
        assert msgs[1]["role"] == "user"
        assert "Build hello.py" in msgs[1]["content"]
        assert ".selffork/plan.json" in msgs[1]["content"]
        assert "/var/data/sandbox/ws" in msgs[1]["content"]

    def test_system_prompt_explains_done_sentinel(self) -> None:
        cfg = CLIAgentConfig(agent="claude-code")
        agent = ClaudeCodeAgent(cfg)
        msgs = agent.compose_initial_messages(prd="x", plan_path="p", workspace="w")
        assert DONE_SENTINEL in msgs[0]["content"]
        sys_lower = msgs[0]["content"].lower()
        assert "tamam" in sys_lower
        assert "bitti" in sys_lower or "done" in sys_lower


class TestBuildCommand:
    def test_first_round_uses_print_flag(self) -> None:
        cfg = CLIAgentConfig(agent="claude-code")
        agent = ClaudeCodeAgent(cfg)
        cmd = agent.build_command(message="hello claude", is_first_round=True)
        assert cmd[0] == "-p"
        assert "--continue" not in cmd
        # claude requires explicit auto-approve flag (unlike opencode which
        # uses its own config file). See project_per_cli_auto_approve_flags.
        assert "--dangerously-skip-permissions" in cmd
        assert cmd[-1] == "hello claude"

    def test_subsequent_round_uses_continue(self) -> None:
        cfg = CLIAgentConfig(agent="claude-code")
        agent = ClaudeCodeAgent(cfg)
        cmd = agent.build_command(message="next step", is_first_round=False)
        assert cmd[0] == "-p"
        assert "--continue" in cmd
        assert "--dangerously-skip-permissions" in cmd
        assert cmd[-1] == "next step"
        # --continue must come before --dangerously-skip-permissions so
        # claude parses the resume flag before the policy flag (order is
        # not strictly required by the CLI, but we want a stable layout
        # for log-grepping and debugging).
        assert cmd.index("--continue") < cmd.index("--dangerously-skip-permissions")

    def test_extra_args_inserted_before_message(self) -> None:
        cfg = CLIAgentConfig(agent="claude-code", extra_args=["--bare"])
        agent = ClaudeCodeAgent(cfg)
        cmd = agent.build_command(message="hi", is_first_round=True)
        assert cmd[-1] == "hi"
        assert "--bare" in cmd
        # extra_args sit between SelfFork-managed flags and the message,
        # matching the OpenCode/Gemini layout.
        assert cmd.index("--bare") < cmd.index("hi")
        assert cmd.index("--dangerously-skip-permissions") < cmd.index("--bare")


class TestBuildEnv:
    def test_does_not_redirect_provider_endpoint(self) -> None:
        # Critical: claude uses its OWN provider config (ANTHROPIC_API_KEY
        # env or claude login). SelfFork must NOT inject its local Gemma
        # endpoint here.
        cfg = CLIAgentConfig(agent="claude-code")
        agent = ClaudeCodeAgent(cfg)
        base = {"PATH": "/usr/bin", "HOME": "/home/y"}
        env = agent.build_env(base_env=base)
        assert "OPENAI_BASE_URL" not in env
        assert "OPENAI_API_KEY" not in env
        assert "ANTHROPIC_BASE_URL" not in env

    def test_passes_through_user_env(self) -> None:
        cfg = CLIAgentConfig(agent="claude-code")
        agent = ClaudeCodeAgent(cfg)
        base = {"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "real-secret-stays"}
        env = agent.build_env(base_env=base)
        assert env["PATH"] == "/usr/bin"
        # User's claude provider key passes through untouched.
        assert env["ANTHROPIC_API_KEY"] == "real-secret-stays"

    def test_disables_color_output(self) -> None:
        cfg = CLIAgentConfig(agent="claude-code")
        agent = ClaudeCodeAgent(cfg)
        env = agent.build_env(base_env={"PATH": "/bin"})
        assert env.get("TERM") == "dumb"
        assert env.get("NO_COLOR") == "1"

    def test_existing_term_not_overwritten(self) -> None:
        cfg = CLIAgentConfig(agent="claude-code")
        agent = ClaudeCodeAgent(cfg)
        env = agent.build_env(base_env={"TERM": "xterm-256color", "NO_COLOR": "0"})
        assert env["TERM"] == "xterm-256color"
        assert env["NO_COLOR"] == "0"


class TestIsSelfForkJrDone:
    @pytest.mark.parametrize(
        "reply",
        [
            DONE_SENTINEL,
            f"All tasks complete.\n{DONE_SENTINEL}",
            f"{DONE_SENTINEL}\n",
            f"Hesap makinesi hazır + test geçti. {DONE_SENTINEL}",
        ],
    )
    def test_sentinel_present_returns_true(self, reply: str) -> None:
        cfg = CLIAgentConfig(agent="claude-code")
        agent = ClaudeCodeAgent(cfg)
        assert agent.is_selffork_jr_done(reply) is True

    @pytest.mark.parametrize(
        "reply",
        [
            "tamam, şu hatayı da düzelt sonra",
            "Done with refactor — now write tests.",
            "Bitti hello.py kısmı. Şimdi pytest ekle.",
            "tamam bitti",
            "DONE",
            "[DONE]",
            "",
        ],
    )
    def test_no_sentinel_returns_false(self, reply: str) -> None:
        cfg = CLIAgentConfig(agent="claude-code")
        agent = ClaudeCodeAgent(cfg)
        assert agent.is_selffork_jr_done(reply) is False
