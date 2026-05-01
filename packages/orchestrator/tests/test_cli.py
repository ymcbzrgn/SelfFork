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
