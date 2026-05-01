"""Unit tests for :class:`OpenCodeAgent` (round-loop architecture)."""

from __future__ import annotations

from pathlib import Path

import pytest

from selffork_orchestrator.cli_agent.opencode import DONE_SENTINEL, OpenCodeAgent
from selffork_shared.config import CLIAgentConfig
from selffork_shared.errors import AgentBinaryNotFoundError


def _make_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


class TestInit:
    def test_validates_agent_field(self) -> None:
        cfg = CLIAgentConfig(agent="claude-code")
        with pytest.raises(ValueError, match="opencode"):
            OpenCodeAgent(cfg)


class TestResolveBinary:
    def test_explicit_path_when_executable(self, tmp_path: Path) -> None:
        fake = tmp_path / "opencode-fake"
        _make_executable(fake)
        cfg = CLIAgentConfig(agent="opencode", binary_path=str(fake))
        agent = OpenCodeAgent(cfg)
        assert agent.resolve_binary() == str(fake)

    def test_explicit_path_missing_raises(self, tmp_path: Path) -> None:
        cfg = CLIAgentConfig(
            agent="opencode",
            binary_path=str(tmp_path / "no-such-binary"),
        )
        agent = OpenCodeAgent(cfg)
        with pytest.raises(AgentBinaryNotFoundError, match="not an executable"):
            agent.resolve_binary()

    def test_explicit_path_not_executable_raises(self, tmp_path: Path) -> None:
        fake = tmp_path / "opencode-non-exec"
        fake.write_text("not executable", encoding="utf-8")
        cfg = CLIAgentConfig(agent="opencode", binary_path=str(fake))
        agent = OpenCodeAgent(cfg)
        with pytest.raises(AgentBinaryNotFoundError):
            agent.resolve_binary()

    def test_falls_back_to_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_dir = tmp_path / "bin"
        fake_dir.mkdir()
        fake = fake_dir / "opencode"
        _make_executable(fake)
        monkeypatch.setenv("PATH", str(fake_dir))
        cfg = CLIAgentConfig(agent="opencode")
        agent = OpenCodeAgent(cfg)
        assert agent.resolve_binary() == str(fake)

    def test_not_found_raises_with_hint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PATH", str(tmp_path / "no-such"))
        monkeypatch.setattr(
            "selffork_orchestrator.cli_agent.opencode._COMMON_INSTALL_PATHS",
            (tmp_path / "fake1", tmp_path / "fake2"),
        )
        cfg = CLIAgentConfig(agent="opencode")
        agent = OpenCodeAgent(cfg)
        with pytest.raises(AgentBinaryNotFoundError, match="install"):
            agent.resolve_binary()


class TestComposeInitialMessages:
    def test_returns_system_then_user(self) -> None:
        cfg = CLIAgentConfig(agent="opencode")
        agent = OpenCodeAgent(cfg)
        msgs = agent.compose_initial_messages(
            prd="Build hello.py",
            plan_path=".selffork/plan.json",
            workspace="/var/data/sandbox/ws",
        )
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert "SelfFork Jr" in msgs[0]["content"]
        assert msgs[1]["role"] == "user"
        # User message must include PRD body, plan path, and workspace.
        assert "Build hello.py" in msgs[1]["content"]
        assert ".selffork/plan.json" in msgs[1]["content"]
        assert "/var/data/sandbox/ws" in msgs[1]["content"]

    def test_system_prompt_explains_done_sentinel(self) -> None:
        cfg = CLIAgentConfig(agent="opencode")
        agent = OpenCodeAgent(cfg)
        msgs = agent.compose_initial_messages(prd="x", plan_path="p", workspace="w")
        assert DONE_SENTINEL in msgs[0]["content"]
        # Must warn that 'tamam'/'bitti'/'done' alone do NOT end the session.
        sys_lower = msgs[0]["content"].lower()
        assert "tamam" in sys_lower
        assert "bitti" in sys_lower or "done" in sys_lower


class TestBuildCommand:
    def test_first_round_uses_run_subcommand(self) -> None:
        cfg = CLIAgentConfig(agent="opencode")
        agent = OpenCodeAgent(cfg)
        cmd = agent.build_command(message="hello opencode", is_first_round=True)
        assert cmd[0] == "run"
        assert "--continue" not in cmd
        # opencode auto-approves via its own ``opencode.json`` config —
        # no SelfFork CLI flag is added (different from claude / gemini).
        assert "--dangerously-skip-permissions" not in cmd
        assert cmd[-1] == "hello opencode"

    def test_subsequent_round_uses_continue(self) -> None:
        cfg = CLIAgentConfig(agent="opencode")
        agent = OpenCodeAgent(cfg)
        cmd = agent.build_command(message="next step", is_first_round=False)
        assert cmd[0] == "run"
        assert "--continue" in cmd
        assert cmd[-1] == "next step"

    def test_extra_args_inserted_before_message(self) -> None:
        cfg = CLIAgentConfig(agent="opencode", extra_args=["-v"])
        agent = OpenCodeAgent(cfg)
        cmd = agent.build_command(message="hi", is_first_round=True)
        assert cmd[-1] == "hi"
        assert "-v" in cmd
        # extra_args should sit before the message but after the SelfFork-managed flags
        assert cmd.index("-v") < cmd.index("hi")


class TestBuildEnv:
    def test_does_not_redirect_openai_endpoint(self) -> None:
        # Critical: opencode uses its OWN provider config (opencode.json /
        # OPENCODE_* env). SelfFork must NOT inject OPENAI_BASE_URL etc.
        cfg = CLIAgentConfig(agent="opencode")
        agent = OpenCodeAgent(cfg)
        base = {"PATH": "/usr/bin", "HOME": "/home/y"}
        env = agent.build_env(base_env=base)
        assert "OPENAI_BASE_URL" not in env
        assert "OPENAI_API_KEY" not in env
        assert "OPENCODE_BASE_URL" not in env

    def test_passes_through_user_env(self) -> None:
        cfg = CLIAgentConfig(agent="opencode")
        agent = OpenCodeAgent(cfg)
        base = {"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "real-secret-stays"}
        env = agent.build_env(base_env=base)
        assert env["PATH"] == "/usr/bin"
        # User's own provider key passes through untouched.
        assert env["ANTHROPIC_API_KEY"] == "real-secret-stays"

    def test_disables_color_output(self) -> None:
        cfg = CLIAgentConfig(agent="opencode")
        agent = OpenCodeAgent(cfg)
        # Use a clean base env so ``setdefault`` actually sets our values.
        env = agent.build_env(base_env={"PATH": "/bin"})
        assert env.get("TERM") == "dumb"
        assert env.get("NO_COLOR") == "1"

    def test_existing_term_not_overwritten(self) -> None:
        cfg = CLIAgentConfig(agent="opencode")
        agent = OpenCodeAgent(cfg)
        env = agent.build_env(base_env={"TERM": "xterm-256color", "NO_COLOR": "0"})
        # We use setdefault so existing values win.
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
        cfg = CLIAgentConfig(agent="opencode")
        agent = OpenCodeAgent(cfg)
        assert agent.is_selffork_jr_done(reply) is True

    @pytest.mark.parametrize(
        "reply",
        [
            "tamam, şu hatayı da düzelt sonra",  # said TO opencode, not session-end
            "Done with refactor — now write tests.",  # said TO opencode
            "Bitti hello.py kısmı. Şimdi pytest ekle.",  # said TO opencode
            "tamam bitti",  # bare phrase, NOT the literal sentinel
            "DONE",  # ALL CAPS but not the sentinel
            "[DONE]",  # similar but missing the SELFFORK: namespace
            "",
        ],
    )
    def test_no_sentinel_returns_false(self, reply: str) -> None:
        cfg = CLIAgentConfig(agent="opencode")
        agent = OpenCodeAgent(cfg)
        assert agent.is_selffork_jr_done(reply) is False
