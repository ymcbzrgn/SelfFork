"""Smoke tests for the ``selffork`` Typer CLI surface.

These tests exercise option parsing, error paths, and version output
without spawning any real subprocess. End-to-end happy-path testing of
``selffork run`` with stubbed runtime/sandbox/agent lives under
``tests/e2e/`` (added in ADR-001 §17 step 11).
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from selffork_orchestrator import __version__
from selffork_orchestrator.cli import app

runner = CliRunner()


class TestHelpAndVersion:
    def test_help_exits_zero(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "selffork" in result.stdout.lower()

    def test_version_prints_and_exits_zero(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        # Typer with no_args_is_help=True exits 2 ("missing command") on
        # the bare invocation but still prints help.
        assert result.exit_code in (0, 2)


class TestRunErrors:
    def test_missing_prd_file_exits_2(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["run", str(tmp_path / "no-such-file.md")])
        assert result.exit_code == 2
        # Typer routes some error text to stderr; CliRunner captures both
        # into ``result.output`` by default.
        assert "PRD file not found" in result.output or "no-such-file" in result.output

    def test_invalid_mode_exits_2(self, tmp_path: Path) -> None:
        prd = tmp_path / "prd.md"
        prd.write_text("# Hello\n", encoding="utf-8")
        result = runner.invoke(app, ["run", str(prd), "--mode", "telepathy"])
        assert result.exit_code == 2
        assert "mode" in result.output.lower()

    def test_missing_config_exits_2(self, tmp_path: Path) -> None:
        prd = tmp_path / "prd.md"
        prd.write_text("hello", encoding="utf-8")
        result = runner.invoke(
            app,
            ["run", str(prd), "--config", str(tmp_path / "no-such.yaml")],
        )
        assert result.exit_code == 2
        assert (
            "configuration error" in result.output.lower() or "not found" in result.output.lower()
        )


class TestRunManyErrors:
    def test_single_prd_rejected(self, tmp_path: Path) -> None:
        prd = tmp_path / "prd.md"
        prd.write_text("hi", encoding="utf-8")
        result = runner.invoke(app, ["run-many", str(prd)])
        assert result.exit_code == 2
        assert "at least two" in result.output.lower()

    def test_missing_prd_file_exits_2(self, tmp_path: Path) -> None:
        prd1 = tmp_path / "prd1.md"
        prd1.write_text("hi", encoding="utf-8")
        result = runner.invoke(app, ["run-many", str(prd1), str(tmp_path / "missing.md")])
        assert result.exit_code == 2
        assert "PRD file not found" in result.output


class TestRunManyHelpers:
    def test_build_child_command_no_config(self, tmp_path: Path) -> None:
        from selffork_orchestrator.cli import _build_child_command

        prd = tmp_path / "p.md"
        cmd = _build_child_command(
            selffork_script=Path("/venv/bin/selffork"),
            prd=prd,
            config_path=None,
            shared_host="127.0.0.1",
            shared_port=8080,
        )
        assert "SELFFORK_RUNTIME__MODE=shared" in cmd
        assert "SELFFORK_RUNTIME__PORT=8080" in cmd
        assert "SELFFORK_RUNTIME__HOST=127.0.0.1" in cmd
        assert "/venv/bin/selffork" in cmd
        assert " run " in cmd
        assert str(prd) in cmd
        assert "--config" not in cmd
        assert cmd.endswith('echo "[SELFFORK:EXIT:$?]"')

    def test_build_child_command_with_config(self, tmp_path: Path) -> None:
        from selffork_orchestrator.cli import _build_child_command

        prd = tmp_path / "p.md"
        cfg = tmp_path / "selffork.yaml"
        cmd = _build_child_command(
            selffork_script=Path("/venv/bin/selffork"),
            prd=prd,
            config_path=cfg,
            shared_host="127.0.0.1",
            shared_port=9000,
        )
        assert "--config" in cmd
        assert str(cfg) in cmd

    def test_build_child_command_quotes_paths_with_spaces(self, tmp_path: Path) -> None:
        from selffork_orchestrator.cli import _build_child_command

        prd = tmp_path / "with space" / "p.md"
        cmd = _build_child_command(
            selffork_script=Path("/venv/bin/selffork"),
            prd=prd,
            config_path=None,
            shared_host="127.0.0.1",
            shared_port=8080,
        )
        # shlex.quote wraps paths containing spaces in single quotes.
        assert "'" in cmd
        assert str(prd) in cmd

    def test_parse_exit_code_returns_last_match(self, tmp_path: Path) -> None:
        from selffork_orchestrator.cli import _parse_exit_code

        log = tmp_path / "p.log"
        log.write_text(
            "lots of stdout\n"
            "[SELFFORK:EXIT:42]\n"
            "(another line — pane kept running for some reason)\n"
            "[SELFFORK:EXIT:0]\n",
            encoding="utf-8",
        )
        # Runner uses the LAST match so a re-run inside the same pane
        # reports the most recent exit, not a stale one.
        assert _parse_exit_code(log) == 0

    def test_parse_exit_code_no_sentinel_returns_none(self, tmp_path: Path) -> None:
        from selffork_orchestrator.cli import _parse_exit_code

        log = tmp_path / "p.log"
        log.write_text("output without exit sentinel\n", encoding="utf-8")
        assert _parse_exit_code(log) is None

    def test_parse_exit_code_missing_file_returns_none(self, tmp_path: Path) -> None:
        from selffork_orchestrator.cli import _parse_exit_code

        assert _parse_exit_code(tmp_path / "no-such.log") is None

    def test_parse_exit_code_handles_negative(self, tmp_path: Path) -> None:
        from selffork_orchestrator.cli import _parse_exit_code

        log = tmp_path / "p.log"
        # ``-15`` corresponds to SIGTERM (process killed by signal). Parser
        # must accept the negative sign so we can distinguish "killed" from
        # "exited cleanly with non-zero code".
        log.write_text("[SELFFORK:EXIT:-15]\n", encoding="utf-8")
        assert _parse_exit_code(log) == -15


# ── _apply_project_routing ────────────────────────────────────────────────────


class TestApplyProjectRouting:
    def test_no_slug_returns_settings_unchanged(self, tmp_path: Path) -> None:
        from selffork_orchestrator.cli import _apply_project_routing
        from selffork_shared.config import SelfForkSettings

        settings = SelfForkSettings()
        result = _apply_project_routing(
            settings,
            project_slug=None,
            projects_root=tmp_path / "projects",
        )
        # No-op when no project slug is supplied — defaults stay intact.
        assert result is settings

    def test_redirects_audit_and_workspace_dirs(self, tmp_path: Path) -> None:
        from selffork_orchestrator.cli import _apply_project_routing
        from selffork_orchestrator.projects.store import ProjectStore
        from selffork_shared.config import SelfForkSettings

        projects_root = tmp_path / "projects"
        ProjectStore(root=projects_root).create(name="My Project", slug="my-project")

        settings = SelfForkSettings()
        result = _apply_project_routing(
            settings,
            project_slug="my-project",
            projects_root=projects_root,
        )

        expected_audit = projects_root / "my-project" / "audit"
        expected_workspace = projects_root / "my-project" / "workspaces"

        assert result.audit.audit_dir == str(expected_audit)
        assert result.sandbox.workspace_root == str(expected_workspace)
        assert expected_audit.is_dir()
        assert expected_workspace.is_dir()

        # Original settings object is left untouched (model_copy semantics).
        assert settings.audit.audit_dir == "~/.selffork/audit"
        assert settings.sandbox.workspace_root == "~/.selffork/workspaces"

    def test_idempotent_on_existing_dirs(self, tmp_path: Path) -> None:
        from selffork_orchestrator.cli import _apply_project_routing
        from selffork_orchestrator.projects.store import ProjectStore
        from selffork_shared.config import SelfForkSettings

        projects_root = tmp_path / "projects"
        ProjectStore(root=projects_root).create(name="P", slug="p")

        settings = SelfForkSettings()
        # Running twice must not raise — directories are mkdir'd with
        # ``exist_ok=True``.
        once = _apply_project_routing(
            settings,
            project_slug="p",
            projects_root=projects_root,
        )
        twice = _apply_project_routing(
            settings,
            project_slug="p",
            projects_root=projects_root,
        )
        assert once.audit.audit_dir == twice.audit.audit_dir
