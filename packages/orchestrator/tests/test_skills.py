"""S-Vision Faz F — SkillInstaller symlink fan-out tests."""

from __future__ import annotations

from pathlib import Path

from selffork_orchestrator.skills import (
    SkillInstaller,
    SkillSyncReport,
    default_canonical_skills_dir,
    default_target_cli_dirs,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _seed_canonical(root: Path, names: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        (root / name).mkdir(parents=True, exist_ok=True)
        (root / name / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")


# ── Defaults ──────────────────────────────────────────────────────────


def test_default_canonical_dir_basename_and_parent() -> None:
    assert default_canonical_skills_dir().name == "skills"
    assert default_canonical_skills_dir().parent.name == ".selffork"


def test_default_target_cli_dirs_cover_four_clis() -> None:
    parents = {t.parent.name for t in default_target_cli_dirs()}
    assert parents == {".claude", ".codex", ".gemini", ".opencode"}


def test_default_target_cli_dirs_all_named_skills() -> None:
    assert all(t.name == "skills" for t in default_target_cli_dirs())


# ── list_skills ───────────────────────────────────────────────────────


def test_list_skills_empty_when_canonical_absent(tmp_path: Path) -> None:
    installer = SkillInstaller(
        canonical_dir=tmp_path / "absent",
        target_dirs=[tmp_path / "t1"],
    )
    assert installer.list_skills() == []


def test_list_skills_returns_subdirs_sorted_and_ignores_files(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "skills"
    _seed_canonical(canonical, ["beta", "alpha", "gamma"])
    (canonical / "README.md").write_text("not a skill", encoding="utf-8")
    installer = SkillInstaller(
        canonical_dir=canonical, target_dirs=[tmp_path / "t1"]
    )
    names = [p.name for p in installer.list_skills()]
    assert names == ["alpha", "beta", "gamma"]


# ── sync_all happy path ──────────────────────────────────────────────


def test_sync_creates_symlinks_in_each_target(tmp_path: Path) -> None:
    canonical = tmp_path / "skills"
    _seed_canonical(canonical, ["s1", "s2"])
    t1 = tmp_path / "target-claude"
    t2 = tmp_path / "target-codex"
    installer = SkillInstaller(canonical_dir=canonical, target_dirs=[t1, t2])
    report = installer.sync_all()
    assert set(report.installed) == {"s1", "s2"}
    assert (t1 / "s1").is_symlink()
    assert (t1 / "s1").resolve() == (canonical / "s1").resolve()
    assert (t2 / "s2").is_symlink()
    # File inside the skill is reachable via the symlinked dir.
    assert (t1 / "s1" / "SKILL.md").read_text(encoding="utf-8").startswith("# s1")


def test_sync_creates_target_dir_on_demand(tmp_path: Path) -> None:
    canonical = tmp_path / "skills"
    _seed_canonical(canonical, ["s1"])
    t1 = tmp_path / "deeply" / "nested" / "absent"
    installer = SkillInstaller(canonical_dir=canonical, target_dirs=[t1])
    installer.sync_all()
    assert t1.is_dir()
    assert (t1 / "s1").is_symlink()


def test_sync_is_idempotent(tmp_path: Path) -> None:
    canonical = tmp_path / "skills"
    _seed_canonical(canonical, ["s1"])
    t1 = tmp_path / "target"
    installer = SkillInstaller(canonical_dir=canonical, target_dirs=[t1])
    installer.sync_all()  # first run installs
    report = installer.sync_all()  # second run skips
    assert "s1" in report.skipped
    assert report.installed == {}
    assert report.conflicts == {}


def test_sync_empty_canonical_returns_empty_report(tmp_path: Path) -> None:
    canonical = tmp_path / "skills"
    canonical.mkdir()
    t1 = tmp_path / "target"
    installer = SkillInstaller(canonical_dir=canonical, target_dirs=[t1])
    report = installer.sync_all()
    assert report.installed == {}
    assert report.skipped == {}
    assert report.conflicts == {}


# ── sync_all conflict paths ──────────────────────────────────────────


def test_sync_reports_conflict_when_symlink_points_elsewhere(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "skills"
    _seed_canonical(canonical, ["s1"])
    other = tmp_path / "other-source"
    other.mkdir()
    t1 = tmp_path / "target"
    t1.mkdir()
    (t1 / "s1").symlink_to(other, target_is_directory=True)
    installer = SkillInstaller(canonical_dir=canonical, target_dirs=[t1])
    report = installer.sync_all()
    assert "s1" in report.conflicts
    reason = report.conflicts["s1"][0][1]
    assert reason.startswith("symlink_to_other")


def test_sync_reports_conflict_when_plain_dir_at_target(tmp_path: Path) -> None:
    canonical = tmp_path / "skills"
    _seed_canonical(canonical, ["s1"])
    t1 = tmp_path / "target"
    t1.mkdir()
    (t1 / "s1").mkdir()  # plain dir blocks the link
    installer = SkillInstaller(canonical_dir=canonical, target_dirs=[t1])
    report = installer.sync_all()
    assert "s1" in report.conflicts
    assert "target_is_dir" in report.conflicts["s1"][0][1]


def test_sync_reports_conflict_when_plain_file_at_target(tmp_path: Path) -> None:
    canonical = tmp_path / "skills"
    _seed_canonical(canonical, ["s1"])
    t1 = tmp_path / "target"
    t1.mkdir()
    (t1 / "s1").write_text("blocking file", encoding="utf-8")
    installer = SkillInstaller(canonical_dir=canonical, target_dirs=[t1])
    report = installer.sync_all()
    assert "target_is_file" in report.conflicts["s1"][0][1]


def test_sync_does_not_overwrite_existing_correct_link_or_conflict(
    tmp_path: Path,
) -> None:
    """A conflict in one target must NOT block install in a sibling target."""
    canonical = tmp_path / "skills"
    _seed_canonical(canonical, ["s1"])
    t_bad = tmp_path / "target-bad"
    t_bad.mkdir()
    (t_bad / "s1").write_text("blocker", encoding="utf-8")
    t_ok = tmp_path / "target-ok"
    installer = SkillInstaller(
        canonical_dir=canonical, target_dirs=[t_bad, t_ok]
    )
    report = installer.sync_all()
    assert "s1" in report.conflicts  # t_bad
    assert "s1" in report.installed  # t_ok succeeded
    assert (t_ok / "s1").is_symlink()


# ── Constructor + default ────────────────────────────────────────────


def test_installer_exposes_canonical_and_targets(tmp_path: Path) -> None:
    targets = [tmp_path / "a", tmp_path / "b"]
    installer = SkillInstaller(canonical_dir=tmp_path, target_dirs=targets)
    assert installer.canonical_dir == tmp_path
    assert installer.target_dirs == targets
    # target_dirs returns a copy so callers can't mutate internal state.
    installer.target_dirs.clear()
    assert installer.target_dirs == targets


def test_default_classmethod_uses_default_dirs() -> None:
    installer = SkillInstaller.default()
    assert installer.canonical_dir == default_canonical_skills_dir()
    assert installer.target_dirs == default_target_cli_dirs()


# ── SkillSyncReport ───────────────────────────────────────────────────


def test_sync_report_default_empty() -> None:
    report = SkillSyncReport()
    assert report.installed == {}
    assert report.skipped == {}
    assert report.conflicts == {}
