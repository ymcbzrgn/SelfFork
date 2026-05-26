"""Pydantic args validation — Faz 3 tools."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from selffork_orchestrator.tools.desktop.tools import (
    DesktopClickArgs,
    DesktopNotificationArgs,
    DesktopPressKeyArgs,
    DesktopSayArgs,
    DesktopScreenshotRegionArgs,
    DesktopTypeArgs,
)
from selffork_orchestrator.tools.github.tools import (
    GithubIssueCreateArgs,
    GithubIssueListArgs,
    GithubPrCreateArgs,
    GithubPrMergeArgs,
    GithubRepoCreateArgs,
)
from selffork_orchestrator.tools.skills.tools import (
    SkillCreateArgs,
    SkillExportArgs,
    SkillInstallArgs,
)

# ---- Desktop ------------------------------------------------------------


def test_desktop_click_non_negative() -> None:
    DesktopClickArgs(x=0, y=0)
    with pytest.raises(ValidationError):
        DesktopClickArgs(x=-1, y=0)


def test_desktop_type_requires_text() -> None:
    with pytest.raises(ValidationError):
        DesktopTypeArgs(text="")


def test_desktop_press_key_required() -> None:
    with pytest.raises(ValidationError):
        DesktopPressKeyArgs(key_combo="")


def test_desktop_screenshot_region_bounds() -> None:
    DesktopScreenshotRegionArgs(x=0, y=0, width=1, height=1)
    DesktopScreenshotRegionArgs(x=0, y=0, width=20_000, height=20_000)
    with pytest.raises(ValidationError):
        DesktopScreenshotRegionArgs(x=0, y=0, width=0, height=1)
    with pytest.raises(ValidationError):
        DesktopScreenshotRegionArgs(x=0, y=0, width=20_001, height=1)


def test_desktop_notification_required() -> None:
    DesktopNotificationArgs(title="T", body="B")
    with pytest.raises(ValidationError):
        DesktopNotificationArgs(title="", body="B")
    with pytest.raises(ValidationError):
        DesktopNotificationArgs(title="T", body="")


def test_desktop_say_rate_bounds() -> None:
    DesktopSayArgs(text="hi", rate=200)
    with pytest.raises(ValidationError):
        DesktopSayArgs(text="hi", rate=9)
    with pytest.raises(ValidationError):
        DesktopSayArgs(text="hi", rate=721)


# ---- GitHub -------------------------------------------------------------


def test_github_issue_list_state_enum() -> None:
    GithubIssueListArgs(repo="ymcbzrgn/x", state="open")
    GithubIssueListArgs(repo="ymcbzrgn/x", state="closed")
    GithubIssueListArgs(repo="ymcbzrgn/x", state="all")
    with pytest.raises(ValidationError):
        GithubIssueListArgs(repo="ymcbzrgn/x", state="other")


def test_github_issue_list_limit_bounds() -> None:
    GithubIssueListArgs(repo="x/y", limit=1)
    GithubIssueListArgs(repo="x/y", limit=200)
    with pytest.raises(ValidationError):
        GithubIssueListArgs(repo="x/y", limit=0)
    with pytest.raises(ValidationError):
        GithubIssueListArgs(repo="x/y", limit=201)


def test_github_issue_create_required() -> None:
    GithubIssueCreateArgs(repo="x/y", title="T", body="B")
    with pytest.raises(ValidationError):
        GithubIssueCreateArgs(repo="x/y", title="", body="B")


def test_github_pr_create_required() -> None:
    GithubPrCreateArgs(repo="x/y", title="T", body="B", head="feature")
    with pytest.raises(ValidationError):
        GithubPrCreateArgs(repo="x/y", title="T", body="B", head="")


def test_github_pr_merge_strategy_enum() -> None:
    GithubPrMergeArgs(repo="x/y", number=1, strategy="merge")
    GithubPrMergeArgs(repo="x/y", number=1, strategy="squash")
    GithubPrMergeArgs(repo="x/y", number=1, strategy="rebase")
    with pytest.raises(ValidationError):
        GithubPrMergeArgs(repo="x/y", number=1, strategy="fast-forward")


def test_github_pr_merge_number_positive() -> None:
    GithubPrMergeArgs(repo="x/y", number=1)
    with pytest.raises(ValidationError):
        GithubPrMergeArgs(repo="x/y", number=0)


def test_github_repo_create_visibility_enum() -> None:
    GithubRepoCreateArgs(name="myrepo", visibility="public")
    GithubRepoCreateArgs(name="myrepo", visibility="private")
    GithubRepoCreateArgs(name="myrepo", visibility="internal")
    with pytest.raises(ValidationError):
        GithubRepoCreateArgs(name="myrepo", visibility="secret")


# ---- Skills -------------------------------------------------------------


def test_skill_install_required() -> None:
    SkillInstallArgs(name="myskill", source="/tmp/skill")
    with pytest.raises(ValidationError):
        SkillInstallArgs(name="", source="x")
    with pytest.raises(ValidationError):
        SkillInstallArgs(name="x", source="")


def test_skill_create_name_pattern() -> None:
    SkillCreateArgs(name="my_skill", description="desc")
    SkillCreateArgs(name="my-skill-2", description="desc")
    # No spaces / dots in name
    with pytest.raises(ValidationError):
        SkillCreateArgs(name="my skill", description="desc")
    with pytest.raises(ValidationError):
        SkillCreateArgs(name="my.skill", description="desc")


def test_skill_export_required() -> None:
    SkillExportArgs(name="x", output_path="/tmp/x.tar.gz")
    with pytest.raises(ValidationError):
        SkillExportArgs(name="", output_path="/tmp/x.tar.gz")
