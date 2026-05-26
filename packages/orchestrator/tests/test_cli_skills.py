"""Tests for the ``selffork skills`` CLI subapp."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from selffork_orchestrator.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_skills_list_no_canonical_dir(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Missing canonical dir is the pre-populate state; print + exit 0."""
    result = runner.invoke(
        app,
        ["skills", "list", "--canonical", str(tmp_path / "absent")],
    )
    assert result.exit_code == 0
    assert "no skills found" in result.stdout


def test_skills_list_empty_canonical(
    runner: CliRunner, tmp_path: Path
) -> None:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    result = runner.invoke(
        app,
        ["skills", "list", "--canonical", str(canonical)],
    )
    assert result.exit_code == 0
    assert "no skills found" in result.stdout


def test_skills_list_with_skills(
    runner: CliRunner, tmp_path: Path
) -> None:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "skill-a").mkdir()
    (canonical / "skill-b").mkdir()
    (canonical / "ignored-file.txt").write_text("not a skill dir")
    result = runner.invoke(
        app,
        ["skills", "list", "--canonical", str(canonical)],
    )
    assert result.exit_code == 0
    assert "Skills (2)" in result.stdout
    assert "skill-a" in result.stdout
    assert "skill-b" in result.stdout
    assert "ignored-file" not in result.stdout


def test_skills_sync_no_canonical_dir(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Missing canonical dir produces a clean message + exit 0."""
    result = runner.invoke(
        app,
        ["skills", "sync", "--canonical", str(tmp_path / "absent")],
    )
    assert result.exit_code == 0
    assert "does not exist yet" in result.stdout


def test_skills_sync_empty_canonical_no_op(
    runner: CliRunner, tmp_path: Path
) -> None:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    target = tmp_path / "target"
    result = runner.invoke(
        app,
        [
            "skills",
            "sync",
            "--canonical",
            str(canonical),
            "--target",
            str(target),
        ],
    )
    assert result.exit_code == 0
    assert "nothing to do" in result.stdout


def test_skills_sync_installs_into_targets(
    runner: CliRunner, tmp_path: Path
) -> None:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "skill-a").mkdir()
    (canonical / "skill-b").mkdir()
    target_one = tmp_path / "target-one"
    target_two = tmp_path / "target-two"
    result = runner.invoke(
        app,
        [
            "skills",
            "sync",
            "--canonical",
            str(canonical),
            "--target",
            str(target_one),
            "--target",
            str(target_two),
        ],
    )
    assert result.exit_code == 0
    assert "Installed (4 links)" in result.stdout
    assert (target_one / "skill-a").is_symlink()
    assert (target_one / "skill-b").is_symlink()
    assert (target_two / "skill-a").is_symlink()
    assert (target_two / "skill-b").is_symlink()
    assert (target_one / "skill-a").resolve() == (canonical / "skill-a").resolve()


def test_skills_sync_idempotent(runner: CliRunner, tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "skill-a").mkdir()
    target = tmp_path / "target"
    args = [
        "skills",
        "sync",
        "--canonical",
        str(canonical),
        "--target",
        str(target),
    ]
    first = runner.invoke(app, args)
    assert first.exit_code == 0
    assert "Installed" in first.stdout
    second = runner.invoke(app, args)
    assert second.exit_code == 0
    assert "Skipped" in second.stdout
    assert "Installed" not in second.stdout or "0 link" in second.stdout


def test_skills_sync_reports_file_conflict(
    runner: CliRunner, tmp_path: Path
) -> None:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "skill-a").mkdir()
    target = tmp_path / "target"
    target.mkdir()
    # Pre-existing PLAIN FILE at target path that blocks the symlink.
    (target / "skill-a").write_text("not a skill — should not be overwritten")
    result = runner.invoke(
        app,
        [
            "skills",
            "sync",
            "--canonical",
            str(canonical),
            "--target",
            str(target),
        ],
    )
    assert result.exit_code == 1
    assert "Conflicts" in result.stdout + result.stderr
    assert "skill-a" in result.stdout + result.stderr
    # Pre-existing file MUST remain untouched.
    assert (target / "skill-a").read_text() == (
        "not a skill — should not be overwritten"
    )


def test_skills_sync_reports_foreign_symlink_conflict(
    runner: CliRunner, tmp_path: Path
) -> None:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "skill-a").mkdir()
    other = tmp_path / "other-source"
    other.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    # Symlink pointing at a DIFFERENT source.
    (target / "skill-a").symlink_to(other, target_is_directory=True)
    result = runner.invoke(
        app,
        [
            "skills",
            "sync",
            "--canonical",
            str(canonical),
            "--target",
            str(target),
        ],
    )
    assert result.exit_code == 1
    assert "symlink_to_other" in (result.stdout + result.stderr)
    # Existing symlink target preserved.
    assert (target / "skill-a").resolve() == other.resolve()
