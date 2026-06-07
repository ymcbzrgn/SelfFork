"""GitHub + Skills handler dispatch (mock gh + filesystem scenarios)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from selffork_orchestrator.tools.github.tools import (
    GithubIssueCreateArgs,
    GithubIssueListArgs,
    GithubPrCreateArgs,
    GithubRepoListArgs,
    _github_issue_create,
    _github_issue_list,
    _github_pr_create,
    _github_repo_list,
)
from selffork_orchestrator.tools.skills.tools import (
    SkillCreateArgs,
    SkillExportArgs,
    SkillInstallArgs,
    SkillListArgs,
    SkillSearchArgs,
    SkillShowArgs,
    SkillSyncArgs,
    SkillUninstallArgs,
    SkillValidateArgs,
    _skill_create,
    _skill_export,
    _skill_install,
    _skill_list,
    _skill_search,
    _skill_show,
    _skill_sync,
    _skill_uninstall,
    _skill_validate,
)

# ---- GitHub: mock _run_gh so we don't hit the real CLI ----


@pytest.fixture(autouse=True)
def mock_gh_run():
    """Mock the gh subprocess call to return success without invoking gh CLI."""

    async def _fake_run(*args, timeout=60.0):  # noqa: ASYNC109 — mock signature
        return {
            "status": "ok",
            "returncode": 0,
            "stdout": "[]",
            "stderr": "",
        }

    with patch("selffork_orchestrator.tools.github._internal._run_gh", _fake_run):
        yield


async def test_github_repo_list(ctx_no_driver_with_warden) -> None:
    result = await _github_repo_list(
        ctx_no_driver_with_warden,
        GithubRepoListArgs(owner="ymcbzrgn"),
    )
    assert result["status"] == "ok"


async def test_github_issue_list(ctx_no_driver_with_warden) -> None:
    result = await _github_issue_list(
        ctx_no_driver_with_warden,
        GithubIssueListArgs(repo="x/y"),
    )
    assert result["status"] == "ok"


async def test_github_issue_create(ctx_no_driver_with_warden) -> None:
    result = await _github_issue_create(
        ctx_no_driver_with_warden,
        GithubIssueCreateArgs(repo="x/y", title="T", body="B"),
    )
    assert result["status"] == "ok"


async def test_github_pr_create(ctx_no_driver_with_warden) -> None:
    result = await _github_pr_create(
        ctx_no_driver_with_warden,
        GithubPrCreateArgs(repo="x/y", title="T", body="B", head="feat"),
    )
    assert result["status"] == "ok"


# ---- Skills: real filesystem scenarios in tmp ----


@pytest.fixture
def canonical_dir(tmp_path):
    """Per-test isolated canonical skills dir."""
    d = tmp_path / "skills"
    d.mkdir()
    return d


async def test_skill_list_empty(ctx_no_driver_with_warden, canonical_dir) -> None:
    result = await _skill_list(
        ctx_no_driver_with_warden,
        SkillListArgs(canonical_dir=str(canonical_dir)),
    )
    assert result["result"]["count"] == 0


async def test_skill_create_and_list(ctx_no_driver_with_warden, canonical_dir) -> None:
    create_result = await _skill_create(
        ctx_no_driver_with_warden,
        SkillCreateArgs(
            name="mytool",
            description="My test skill",
            canonical_dir=str(canonical_dir),
        ),
    )
    assert create_result["result"]["status"] == "ok"
    list_result = await _skill_list(
        ctx_no_driver_with_warden,
        SkillListArgs(canonical_dir=str(canonical_dir)),
    )
    assert list_result["result"]["count"] == 1
    assert "mytool" in list_result["result"]["names"]


async def test_skill_create_idempotent(
    ctx_no_driver_with_warden,
    canonical_dir,
) -> None:
    await _skill_create(
        ctx_no_driver_with_warden,
        SkillCreateArgs(
            name="x",
            description="d",
            canonical_dir=str(canonical_dir),
        ),
    )
    second = await _skill_create(
        ctx_no_driver_with_warden,
        SkillCreateArgs(
            name="x",
            description="d",
            canonical_dir=str(canonical_dir),
        ),
    )
    assert second["result"]["status"] == "already_exists"


async def test_skill_show(ctx_no_driver_with_warden, canonical_dir) -> None:
    await _skill_create(
        ctx_no_driver_with_warden,
        SkillCreateArgs(
            name="x",
            description="d",
            canonical_dir=str(canonical_dir),
        ),
    )
    result = await _skill_show(
        ctx_no_driver_with_warden,
        SkillShowArgs(name="x", canonical_dir=str(canonical_dir)),
    )
    assert result["result"]["exists"] is True
    assert "SKILL.md" in result["result"]["files"]


async def test_skill_show_missing(ctx_no_driver_with_warden, canonical_dir) -> None:
    result = await _skill_show(
        ctx_no_driver_with_warden,
        SkillShowArgs(name="ghost", canonical_dir=str(canonical_dir)),
    )
    assert result["result"]["exists"] is False


async def test_skill_validate_valid(ctx_no_driver_with_warden, canonical_dir) -> None:
    await _skill_create(
        ctx_no_driver_with_warden,
        SkillCreateArgs(
            name="v",
            description="d",
            canonical_dir=str(canonical_dir),
        ),
    )
    result = await _skill_validate(
        ctx_no_driver_with_warden,
        SkillValidateArgs(name="v", canonical_dir=str(canonical_dir)),
    )
    assert result["result"]["valid"] is True


async def test_skill_validate_missing(ctx_no_driver_with_warden, canonical_dir) -> None:
    result = await _skill_validate(
        ctx_no_driver_with_warden,
        SkillValidateArgs(name="ghost", canonical_dir=str(canonical_dir)),
    )
    assert result["result"]["valid"] is False
    assert result["result"]["reason"] == "skill_dir_missing"


async def test_skill_uninstall_removes_dir(
    ctx_no_driver_with_warden,
    canonical_dir,
) -> None:
    await _skill_create(
        ctx_no_driver_with_warden,
        SkillCreateArgs(
            name="bye",
            description="d",
            canonical_dir=str(canonical_dir),
        ),
    )
    result = await _skill_uninstall(
        ctx_no_driver_with_warden,
        SkillUninstallArgs(name="bye", canonical_dir=str(canonical_dir)),
    )
    assert result["result"]["status"] == "ok"
    assert not (canonical_dir / "bye").exists()


async def test_skill_uninstall_not_installed(
    ctx_no_driver_with_warden,
    canonical_dir,
) -> None:
    result = await _skill_uninstall(
        ctx_no_driver_with_warden,
        SkillUninstallArgs(name="ghost", canonical_dir=str(canonical_dir)),
    )
    assert result["result"]["status"] == "not_installed"


async def test_skill_search_in_manifest(
    ctx_no_driver_with_warden,
    canonical_dir,
) -> None:
    await _skill_create(
        ctx_no_driver_with_warden,
        SkillCreateArgs(
            name="found",
            description="searchable description",
            canonical_dir=str(canonical_dir),
        ),
    )
    result = await _skill_search(
        ctx_no_driver_with_warden,
        SkillSearchArgs(query="searchable", canonical_dir=str(canonical_dir)),
    )
    assert result["result"]["count"] == 1


async def test_skill_export_creates_tarball(
    ctx_no_driver_with_warden,
    canonical_dir,
    tmp_path,
) -> None:
    await _skill_create(
        ctx_no_driver_with_warden,
        SkillCreateArgs(
            name="exp",
            description="d",
            canonical_dir=str(canonical_dir),
        ),
    )
    out = tmp_path / "exp.tar.gz"
    result = await _skill_export(
        ctx_no_driver_with_warden,
        SkillExportArgs(
            name="exp",
            output_path=str(out),
            canonical_dir=str(canonical_dir),
        ),
    )
    assert result["result"]["status"] == "ok"
    assert out.is_file()
    assert out.stat().st_size > 0


async def test_skill_sync_custom_targets(
    ctx_no_driver_with_warden,
    canonical_dir,
    tmp_path,
) -> None:
    """Sync against tmp target dirs so we don't pollute the real CLI skill dirs."""
    await _skill_create(
        ctx_no_driver_with_warden,
        SkillCreateArgs(
            name="syncme",
            description="d",
            canonical_dir=str(canonical_dir),
        ),
    )
    target_a = tmp_path / "target_a"
    target_b = tmp_path / "target_b"
    result = await _skill_sync(
        ctx_no_driver_with_warden,
        SkillSyncArgs(
            canonical_dir=str(canonical_dir),
            target_dirs=[str(target_a), str(target_b)],
        ),
    )
    assert isinstance(result["result"]["installed"], dict)
    assert (target_a / "syncme").is_symlink()
    assert (target_b / "syncme").is_symlink()


async def test_skill_install_local_path(
    ctx_no_driver_with_warden,
    canonical_dir,
    tmp_path,
) -> None:
    """Install a skill from a local path."""
    source = tmp_path / "src_skill"
    source.mkdir()
    (source / "SKILL.md").write_text("---\nname: imported\ndescription: x\n---\n")
    result = await _skill_install(
        ctx_no_driver_with_warden,
        SkillInstallArgs(
            name="imported",
            source=str(source),
            canonical_dir=str(canonical_dir),
        ),
    )
    assert result["result"]["status"] == "ok"
    assert (canonical_dir / "imported" / "SKILL.md").is_file()
