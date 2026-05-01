"""Unit tests for :class:`GeminiCliAgent` (round-loop architecture)."""

from __future__ import annotations

from pathlib import Path

import pytest

from selffork_orchestrator.cli_agent.gemini_cli import (
    DONE_SENTINEL,
    GeminiCliAgent,
)
from selffork_shared.config import CLIAgentConfig
from selffork_shared.errors import AgentBinaryNotFoundError


def _make_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


class TestInit:
    def test_validates_agent_field(self) -> None:
        cfg = CLIAgentConfig(agent="opencode")
        with pytest.raises(ValueError, match="gemini-cli"):
            GeminiCliAgent(cfg)


class TestResolveBinary:
    def test_explicit_path_when_executable(self, tmp_path: Path) -> None:
        fake = tmp_path / "gemini-fake"
        _make_executable(fake)
        cfg = CLIAgentConfig(agent="gemini-cli", binary_path=str(fake))
        agent = GeminiCliAgent(cfg)
        assert agent.resolve_binary() == str(fake)

    def test_explicit_path_missing_raises(self, tmp_path: Path) -> None:
        cfg = CLIAgentConfig(
            agent="gemini-cli",
            binary_path=str(tmp_path / "no-such-binary"),
        )
        agent = GeminiCliAgent(cfg)
        with pytest.raises(AgentBinaryNotFoundError, match="not an executable"):
            agent.resolve_binary()

    def test_explicit_path_not_executable_raises(self, tmp_path: Path) -> None:
        fake = tmp_path / "gemini-non-exec"
        fake.write_text("not executable", encoding="utf-8")
        cfg = CLIAgentConfig(agent="gemini-cli", binary_path=str(fake))
        agent = GeminiCliAgent(cfg)
        with pytest.raises(AgentBinaryNotFoundError):
            agent.resolve_binary()

    def test_falls_back_to_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_dir = tmp_path / "bin"
        fake_dir.mkdir()
        fake = fake_dir / "gemini"
        _make_executable(fake)
        monkeypatch.setenv("PATH", str(fake_dir))
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
        assert agent.resolve_binary() == str(fake)

    def test_not_found_raises_with_hint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PATH", str(tmp_path / "no-such"))
        monkeypatch.setattr(
            "selffork_orchestrator.cli_agent.gemini_cli._COMMON_INSTALL_PATHS",
            (tmp_path / "fake1", tmp_path / "fake2"),
        )
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
        with pytest.raises(AgentBinaryNotFoundError, match="install"):
            agent.resolve_binary()


class TestComposeInitialMessages:
    def test_returns_system_then_user(self) -> None:
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
        msgs = agent.compose_initial_messages(
            prd="Build hello.py",
            plan_path=".selffork/plan.json",
            workspace="/var/data/sandbox/ws",
        )
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert "SelfFork Jr" in msgs[0]["content"]
        # System prompt names the CLI being driven so SelfFork Jr can
        # address it correctly.
        assert "gemini" in msgs[0]["content"]
        assert msgs[1]["role"] == "user"
        assert "Build hello.py" in msgs[1]["content"]
        assert ".selffork/plan.json" in msgs[1]["content"]
        assert "/var/data/sandbox/ws" in msgs[1]["content"]

    def test_system_prompt_explains_done_sentinel(self) -> None:
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
        msgs = agent.compose_initial_messages(prd="x", plan_path="p", workspace="w")
        assert DONE_SENTINEL in msgs[0]["content"]
        sys_lower = msgs[0]["content"].lower()
        assert "tamam" in sys_lower
        assert "bitti" in sys_lower or "done" in sys_lower


class TestBuildCommand:
    def test_first_round_uses_prompt_flag(self) -> None:
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
        cmd = agent.build_command(message="hello gemini", is_first_round=True)
        # gemini's positional prompt comes after -p; first round has no
        # --resume because there is no prior session yet.
        assert "-p" in cmd
        assert "--resume" not in cmd
        # ``--approval-mode yolo`` is the modern non-deprecated form of
        # the auto-approve flag (the older ``-y``/``--yolo`` short alias
        # is deprecated upstream).
        assert "--approval-mode" in cmd
        ap_idx = cmd.index("--approval-mode")
        assert cmd[ap_idx + 1] == "yolo"
        assert cmd[-1] == "hello gemini"

    def test_first_round_includes_skip_trust(self) -> None:
        # ``--skip-trust`` is mandatory for unattended runs in fresh
        # workspaces — without it gemini downgrades ``--approval-mode yolo``
        # to ``default`` because the cwd is not in the trusted list.
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
        cmd = agent.build_command(message="x", is_first_round=True)
        assert "--skip-trust" in cmd

    def test_subsequent_round_uses_resume_latest(self) -> None:
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
        cmd = agent.build_command(message="next step", is_first_round=False)
        assert "--resume" in cmd
        resume_idx = cmd.index("--resume")
        assert cmd[resume_idx + 1] == "latest"
        # Resume must come before -p so gemini parses the session-restore
        # flag before the prompt body.
        assert cmd.index("--resume") < cmd.index("-p")
        # ``--skip-trust`` stays present on continuation rounds too — the
        # cwd is the same untrusted workspace.
        assert "--skip-trust" in cmd
        assert cmd[-1] == "next step"

    def test_uses_yolo_approval_mode_not_deprecated_short_flag(self) -> None:
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
        cmd = agent.build_command(message="x", is_first_round=True)
        # Forward-looking: prefer ``--approval-mode yolo`` over the
        # deprecated ``--yolo`` / ``-y`` short alias.
        assert "--yolo" not in cmd
        assert "-y" not in cmd

    def test_extra_args_inserted_before_message(self) -> None:
        cfg = CLIAgentConfig(
            agent="gemini-cli",
            extra_args=["--output-format", "text"],
        )
        agent = GeminiCliAgent(cfg)
        cmd = agent.build_command(message="hi", is_first_round=True)
        assert cmd[-1] == "hi"
        assert "--output-format" in cmd
        assert cmd.index("--output-format") < cmd.index("hi")
        # extra_args sit after SelfFork-managed flags.
        assert cmd.index("--approval-mode") < cmd.index("--output-format")


class TestBuildEnv:
    def test_does_not_redirect_provider_endpoint(self) -> None:
        # Critical: gemini uses its OWN provider config (Google login or
        # GEMINI_API_KEY). SelfFork must NOT inject its local Gemma
        # endpoint here.
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
        base = {"PATH": "/usr/bin", "HOME": "/home/y"}
        env = agent.build_env(base_env=base)
        assert "OPENAI_BASE_URL" not in env
        assert "OPENAI_API_KEY" not in env
        assert "GEMINI_BASE_URL" not in env

    def test_passes_through_user_env(self) -> None:
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
        base = {"PATH": "/usr/bin", "GEMINI_API_KEY": "real-secret-stays"}
        env = agent.build_env(base_env=base)
        assert env["PATH"] == "/usr/bin"
        # User's gemini provider key passes through untouched.
        assert env["GEMINI_API_KEY"] == "real-secret-stays"

    def test_disables_color_output(self) -> None:
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
        env = agent.build_env(base_env={"PATH": "/bin"})
        assert env.get("TERM") == "dumb"
        assert env.get("NO_COLOR") == "1"

    def test_existing_term_not_overwritten(self) -> None:
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
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
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
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
        cfg = CLIAgentConfig(agent="gemini-cli")
        agent = GeminiCliAgent(cfg)
        assert agent.is_selffork_jr_done(reply) is False
