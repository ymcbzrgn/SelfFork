"""GitHub tools — gh CLI subprocess wrappers (15 tools)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.github._internal import _invoke_gh

__all__ = [
    "GithubIssueCloseArgs",
    "GithubIssueCommentArgs",
    "GithubIssueCreateArgs",
    "GithubIssueListArgs",
    "GithubIssueViewArgs",
    "GithubPrCreateArgs",
    "GithubPrListArgs",
    "GithubPrMergeArgs",
    "GithubPrViewArgs",
    "GithubRepoCloneArgs",
    "GithubRepoCreateArgs",
    "GithubRepoForkArgs",
    "GithubRepoListArgs",
    "GithubRepoViewArgs",
    "GithubWorkflowListArgs",
    "GithubWorkflowRunArgs",
    "build_github_tools_inner",
]


# ---- Args ----------------------------------------------------------------


class GithubRepoListArgs(ToolArgs):
    owner: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=30, ge=1, le=200)


class GithubRepoViewArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255, description="owner/name")


class GithubRepoCloneArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)
    target_dir: str | None = Field(default=None, max_length=4096)


class GithubRepoForkArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)
    org: str | None = Field(default=None, max_length=128)


class GithubRepoCreateArgs(ToolArgs):
    name: str = Field(min_length=1, max_length=128)
    visibility: Literal["public", "private", "internal"] = "private"
    description: str | None = Field(default=None, max_length=1024)


class GithubIssueListArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)
    state: Literal["open", "closed", "all"] = "open"
    limit: int = Field(default=30, ge=1, le=200)
    label: str | None = Field(default=None, max_length=128)


class GithubIssueCreateArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(max_length=64_000)
    labels: list[str] | None = Field(default=None, max_length=20)


class GithubIssueViewArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)
    number: int = Field(ge=1)


class GithubIssueCommentArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)
    number: int = Field(ge=1)
    body: str = Field(min_length=1, max_length=64_000)


class GithubIssueCloseArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)
    number: int = Field(ge=1)
    comment: str | None = Field(default=None, max_length=64_000)


class GithubPrListArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)
    state: Literal["open", "closed", "merged", "all"] = "open"
    limit: int = Field(default=30, ge=1, le=200)


class GithubPrCreateArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(max_length=64_000)
    head: str = Field(min_length=1, max_length=128, description="source branch")
    base: str = Field(default="main", min_length=1, max_length=128)
    draft: bool = False


class GithubPrViewArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)
    number: int = Field(ge=1)


class GithubPrMergeArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)
    number: int = Field(ge=1)
    strategy: Literal["merge", "squash", "rebase"] = "merge"
    delete_branch: bool = False


class GithubWorkflowListArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)


class GithubWorkflowRunArgs(ToolArgs):
    repo: str = Field(min_length=1, max_length=255)
    workflow: str = Field(min_length=1, max_length=128, description="name or ID")
    ref: str = Field(default="main", min_length=1, max_length=128)


# ---- Handlers ------------------------------------------------------------


async def _github_repo_list(ctx: ToolContext, args: GithubRepoListArgs) -> dict[str, Any]:
    cmd = ["repo", "list"]
    if args.owner:
        cmd.append(args.owner)
    cmd += ["--limit", str(args.limit), "--json", "name,owner,description,visibility,url"]
    return await _invoke_gh(
        ctx, action_type="github.repo_list", target_uri=args.owner,
        args_summary={"owner": args.owner, "limit": args.limit},
        cmd=cmd, timeout=30.0,
    )


async def _github_repo_view(ctx: ToolContext, args: GithubRepoViewArgs) -> dict[str, Any]:
    cmd = ["repo", "view", args.repo, "--json",
           "name,owner,description,visibility,defaultBranchRef,url,createdAt,updatedAt"]
    return await _invoke_gh(
        ctx, action_type="github.repo_view", target_uri=args.repo,
        args_summary={"repo": args.repo}, cmd=cmd, timeout=30.0,
    )


async def _github_repo_clone(ctx: ToolContext, args: GithubRepoCloneArgs) -> dict[str, Any]:
    cmd = ["repo", "clone", args.repo]
    if args.target_dir:
        cmd.append(args.target_dir)
    return await _invoke_gh(
        ctx, action_type="github.repo_clone", target_uri=args.repo,
        args_summary={"repo": args.repo, "target_dir": args.target_dir},
        cmd=cmd, timeout=300.0,
    )


async def _github_repo_fork(ctx: ToolContext, args: GithubRepoForkArgs) -> dict[str, Any]:
    cmd = ["repo", "fork", args.repo, "--clone=false"]
    if args.org:
        cmd += ["--org", args.org]
    return await _invoke_gh(
        ctx, action_type="github.repo_fork", target_uri=args.repo,
        args_summary={"repo": args.repo, "org": args.org},
        cmd=cmd, timeout=60.0,
    )


async def _github_repo_create(ctx: ToolContext, args: GithubRepoCreateArgs) -> dict[str, Any]:
    cmd = ["repo", "create", args.name, f"--{args.visibility}"]
    if args.description:
        cmd += ["--description", args.description]
    cmd.append("--confirm")
    return await _invoke_gh(
        ctx, action_type="github.repo_create", target_uri=args.name,
        args_summary={
            "name": args.name, "visibility": args.visibility,
            "has_description": args.description is not None,
        },
        cmd=cmd, timeout=60.0,
    )


async def _github_issue_list(ctx: ToolContext, args: GithubIssueListArgs) -> dict[str, Any]:
    cmd = ["issue", "list", "--repo", args.repo, "--state", args.state,
           "--limit", str(args.limit), "--json", "number,title,state,author,labels,createdAt"]
    if args.label:
        cmd += ["--label", args.label]
    return await _invoke_gh(
        ctx, action_type="github.issue_list", target_uri=args.repo,
        args_summary={
            "repo": args.repo, "state": args.state, "limit": args.limit,
            "label": args.label,
        },
        cmd=cmd, timeout=30.0,
    )


async def _github_issue_create(ctx: ToolContext, args: GithubIssueCreateArgs) -> dict[str, Any]:
    cmd = ["issue", "create", "--repo", args.repo,
           "--title", args.title, "--body", args.body]
    for label in (args.labels or []):
        cmd += ["--label", label]
    return await _invoke_gh(
        ctx, action_type="github.issue_create", target_uri=args.repo,
        args_summary={
            "repo": args.repo, "title_len": len(args.title),
            "body_len": len(args.body), "label_count": len(args.labels or []),
        },
        cmd=cmd, timeout=30.0,
    )


async def _github_issue_view(ctx: ToolContext, args: GithubIssueViewArgs) -> dict[str, Any]:
    cmd = ["issue", "view", str(args.number), "--repo", args.repo,
           "--json", "number,title,body,state,author,labels,comments,createdAt"]
    return await _invoke_gh(
        ctx, action_type="github.issue_view",
        target_uri=f"{args.repo}#{args.number}",
        args_summary={"repo": args.repo, "number": args.number},
        cmd=cmd, timeout=30.0,
    )


async def _github_issue_comment(ctx: ToolContext, args: GithubIssueCommentArgs) -> dict[str, Any]:
    cmd = ["issue", "comment", str(args.number), "--repo", args.repo, "--body", args.body]
    return await _invoke_gh(
        ctx, action_type="github.issue_comment",
        target_uri=f"{args.repo}#{args.number}",
        args_summary={
            "repo": args.repo, "number": args.number, "body_len": len(args.body),
        },
        cmd=cmd, timeout=30.0,
    )


async def _github_issue_close(ctx: ToolContext, args: GithubIssueCloseArgs) -> dict[str, Any]:
    cmd = ["issue", "close", str(args.number), "--repo", args.repo]
    if args.comment:
        cmd += ["--comment", args.comment]
    return await _invoke_gh(
        ctx, action_type="github.issue_close",
        target_uri=f"{args.repo}#{args.number}",
        args_summary={
            "repo": args.repo, "number": args.number,
            "has_comment": args.comment is not None,
        },
        cmd=cmd, timeout=30.0,
    )


async def _github_pr_list(ctx: ToolContext, args: GithubPrListArgs) -> dict[str, Any]:
    cmd = ["pr", "list", "--repo", args.repo, "--state", args.state,
           "--limit", str(args.limit), "--json",
           "number,title,state,author,headRefName,baseRefName,isDraft,createdAt"]
    return await _invoke_gh(
        ctx, action_type="github.pr_list", target_uri=args.repo,
        args_summary={"repo": args.repo, "state": args.state, "limit": args.limit},
        cmd=cmd, timeout=30.0,
    )


async def _github_pr_create(ctx: ToolContext, args: GithubPrCreateArgs) -> dict[str, Any]:
    cmd = ["pr", "create", "--repo", args.repo,
           "--title", args.title, "--body", args.body,
           "--head", args.head, "--base", args.base]
    if args.draft:
        cmd.append("--draft")
    return await _invoke_gh(
        ctx, action_type="github.pr_create", target_uri=args.repo,
        args_summary={
            "repo": args.repo, "title_len": len(args.title),
            "body_len": len(args.body),
            "head": args.head, "base": args.base, "draft": args.draft,
        },
        cmd=cmd, timeout=60.0,
    )


async def _github_pr_view(ctx: ToolContext, args: GithubPrViewArgs) -> dict[str, Any]:
    cmd = ["pr", "view", str(args.number), "--repo", args.repo,
           "--json",
           "number,title,body,state,author,headRefName,baseRefName,"
           "isDraft,mergeable,reviewDecision,createdAt"]
    return await _invoke_gh(
        ctx, action_type="github.pr_view",
        target_uri=f"{args.repo}#{args.number}",
        args_summary={"repo": args.repo, "number": args.number},
        cmd=cmd, timeout=30.0,
    )


async def _github_pr_merge(ctx: ToolContext, args: GithubPrMergeArgs) -> dict[str, Any]:
    cmd = ["pr", "merge", str(args.number), "--repo", args.repo,
           f"--{args.strategy}"]
    if args.delete_branch:
        cmd.append("--delete-branch")
    return await _invoke_gh(
        ctx, action_type="github.pr_merge",
        target_uri=f"{args.repo}#{args.number}",
        args_summary={
            "repo": args.repo, "number": args.number,
            "strategy": args.strategy, "delete_branch": args.delete_branch,
        },
        cmd=cmd, timeout=120.0,
    )


async def _github_workflow_list(
    ctx: ToolContext, args: GithubWorkflowListArgs,
) -> dict[str, Any]:
    cmd = ["workflow", "list", "--repo", args.repo,
           "--json", "id,name,state,path"]
    return await _invoke_gh(
        ctx, action_type="github.workflow_list", target_uri=args.repo,
        args_summary={"repo": args.repo}, cmd=cmd, timeout=30.0,
    )


async def _github_workflow_run(
    ctx: ToolContext, args: GithubWorkflowRunArgs,
) -> dict[str, Any]:
    cmd = ["workflow", "run", args.workflow, "--repo", args.repo, "--ref", args.ref]
    return await _invoke_gh(
        ctx, action_type="github.workflow_run", target_uri=args.repo,
        args_summary={
            "repo": args.repo, "workflow": args.workflow, "ref": args.ref,
        },
        cmd=cmd, timeout=60.0,
    )


def build_github_tools_inner() -> list[ToolSpec[Any]]:
    return [
        # Eager (3) — agentic-loop self-commit + status checks
        ToolSpec(
            name="github_pr_create",
            description="Create a pull request via `gh pr create`.",
            args_model=GithubPrCreateArgs, handler=_github_pr_create,
            defer_loading=False,
        ),
        ToolSpec(
            name="github_issue_create",
            description="Create a GitHub issue via `gh issue create`.",
            args_model=GithubIssueCreateArgs, handler=_github_issue_create,
            defer_loading=False,
        ),
        ToolSpec(
            name="github_issue_list",
            description="List GitHub issues in a repo via `gh issue list`.",
            args_model=GithubIssueListArgs, handler=_github_issue_list,
            defer_loading=False,
        ),
        # Deferred (12)
        ToolSpec(
            name="github_repo_list",
            description="List GitHub repos for an owner (or the authed user).",
            args_model=GithubRepoListArgs, handler=_github_repo_list,
            defer_loading=True,
        ),
        ToolSpec(
            name="github_repo_view",
            description="View a GitHub repo's metadata as JSON.",
            args_model=GithubRepoViewArgs, handler=_github_repo_view,
            defer_loading=True,
        ),
        ToolSpec(
            name="github_repo_clone",
            description="Clone a GitHub repo to a host directory.",
            args_model=GithubRepoCloneArgs, handler=_github_repo_clone,
            defer_loading=True,
        ),
        ToolSpec(
            name="github_repo_fork",
            description="Fork a GitHub repo (no clone; pass --org to fork into an org).",
            args_model=GithubRepoForkArgs, handler=_github_repo_fork,
            defer_loading=True,
        ),
        ToolSpec(
            name="github_repo_create",
            description=(
                "Create a new GitHub repo with chosen visibility (public/private/internal)."
            ),
            args_model=GithubRepoCreateArgs, handler=_github_repo_create,
            defer_loading=True,
        ),
        ToolSpec(
            name="github_issue_view",
            description="View a GitHub issue body + comments as JSON.",
            args_model=GithubIssueViewArgs, handler=_github_issue_view,
            defer_loading=True,
        ),
        ToolSpec(
            name="github_issue_comment",
            description="Add a comment to a GitHub issue.",
            args_model=GithubIssueCommentArgs, handler=_github_issue_comment,
            defer_loading=True,
        ),
        ToolSpec(
            name="github_issue_close",
            description="Close a GitHub issue (optionally with a closing comment).",
            args_model=GithubIssueCloseArgs, handler=_github_issue_close,
            defer_loading=True,
        ),
        ToolSpec(
            name="github_pr_list",
            description="List GitHub pull requests by state.",
            args_model=GithubPrListArgs, handler=_github_pr_list,
            defer_loading=True,
        ),
        ToolSpec(
            name="github_pr_view",
            description="View a GitHub PR metadata + review state as JSON.",
            args_model=GithubPrViewArgs, handler=_github_pr_view,
            defer_loading=True,
        ),
        ToolSpec(
            name="github_pr_merge",
            description=(
                "Merge a GitHub PR via merge / squash / rebase strategy. "
                "T2-risk; warden gates."
            ),
            args_model=GithubPrMergeArgs, handler=_github_pr_merge,
            defer_loading=True,
        ),
        ToolSpec(
            name="github_workflow_list",
            description="List GitHub Actions workflows in a repo.",
            args_model=GithubWorkflowListArgs, handler=_github_workflow_list,
            defer_loading=True,
        ),
        ToolSpec(
            name="github_workflow_run",
            description="Trigger a GitHub Actions workflow_dispatch by name/ID + ref.",
            args_model=GithubWorkflowRunArgs, handler=_github_workflow_run,
            defer_loading=True,
        ),
    ]
