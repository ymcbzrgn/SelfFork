"""SelfFork Jr auto-PR tool — open a GitHub PR via the ``gh`` CLI.

ADR-010 §1 MUST (S-Vision Faz E): after committing + pushing a feature
branch, Self Jr can invoke ``auto_pr_create`` to open a PR against
``base``. The push-to-main + merge gates stay with the operator
(MANDATE 1 + S3 warden) — feature-branch push + PR open are reversible,
so the tool runs ``gh pr create`` directly without a soft-confirm wrap.

The handler wraps the ``gh pr create`` subprocess + extracts the URL and
number from its stdout. ``gh`` itself handles auth (operator
pre-authenticated). Missing ``gh`` returns a structured ``missing_binary``
payload rather than crashing; a non-zero ``gh`` exit, a timeout, or
output without a recognisable PR URL all surface as distinct ``status``
values so Self Jr can react.

The tool is sync — ``gh pr create`` is a quick one-shot and the existing
tool registry runs sync handlers without a thread-pool hop.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec

__all__ = ["build_auto_pr_tools"]


# ── auto_pr_create ───────────────────────────────────────────────────────────


class _AutoPRCreateArgs(ToolArgs):
    """Args for ``auto_pr_create``."""

    title: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "PR title — imperative + scoped (e.g. 'Add login flow'). Required, max 200 chars."
        ),
    )
    body: str = Field(
        min_length=1,
        max_length=20_000,
        description=(
            "PR body in Markdown. Include WHAT changed + WHY. Wrap any test "
            "evidence under a `### Tests` heading. Required."
        ),
    )
    base: str = Field(
        default="main",
        min_length=1,
        max_length=80,
        description="Base branch the PR targets (default: ``main``).",
    )
    head: str | None = Field(
        default=None,
        max_length=120,
        description=(
            "Source branch. ``None`` defers to ``gh`` (= current checked-out "
            "branch). Pass an explicit value when the current branch is not "
            "what should be PR'd."
        ),
    )
    draft: bool = Field(
        default=False,
        description=(
            "Open as a draft PR (no review request; not eligible for "
            "auto-merge). Use while the work is in-flight."
        ),
    )


_PR_URL_RE = re.compile(r"https://github\.com/[^\s]+/pull/(\d+)")
_GH_TIMEOUT_SECONDS = 60


def _gh_binary() -> str | None:
    """Locate ``gh`` on PATH; ``None`` when missing so the handler can fail clean."""
    return shutil.which("gh")


def _auto_pr_create_handler(
    ctx: ToolContext,
    args: _AutoPRCreateArgs,
) -> dict[str, Any]:
    del ctx  # ToolContext not consumed — gh handles auth + state.
    binary = _gh_binary()
    if binary is None:
        return {
            "status": "missing_binary",
            "error": ("gh CLI not found on PATH; install + authenticate (`gh auth login`) first"),
        }

    cmd = [
        binary,
        "pr",
        "create",
        "--title",
        args.title,
        "--body",
        args.body,
        "--base",
        args.base,
    ]
    if args.head is not None:
        cmd.extend(["--head", args.head])
    if args.draft:
        cmd.append("--draft")

    try:
        proc = subprocess.run(  # noqa: S603 — list args, shell=False, binary via shutil.which
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=_GH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "timeout_seconds": _GH_TIMEOUT_SECONDS,
            "error": (
                f"gh pr create exceeded the {_GH_TIMEOUT_SECONDS}s budget; "
                "the network or GitHub may be slow"
            ),
        }

    if proc.returncode != 0:
        return {
            "status": "gh_error",
            "exit_code": proc.returncode,
            "stderr": proc.stderr.strip()[:2_000],
            "stdout": proc.stdout.strip()[:2_000],
        }

    url_match = _PR_URL_RE.search(proc.stdout)
    if url_match is None:
        return {
            "status": "no_url",
            "stdout": proc.stdout.strip()[:2_000],
            "stderr": proc.stderr.strip()[:2_000],
            "error": "gh pr create succeeded but emitted no PR URL on stdout",
        }
    return {
        "status": "ok",
        "url": url_match.group(0),
        "number": int(url_match.group(1)),
        "base": args.base,
        "head": args.head,
        "draft": args.draft,
    }


def build_auto_pr_tools() -> list[ToolSpec[Any]]:
    """Return the auto-PR tool surface (ADR-010 §1 MUST, S-Vision Faz E)."""
    return [
        ToolSpec(
            name="auto_pr_create",
            description=(
                "Open a GitHub PR via the ``gh`` CLI. Use AFTER the feature "
                "branch is committed + pushed; the PR review is the "
                "operator's gate before merge (MANDATE 1). Feature-branch "
                "push + PR open are reversible — no warden soft-confirm. "
                "Returns the new PR URL + number on success, or a structured "
                "``missing_binary`` / ``gh_error`` / ``timeout`` / ``no_url`` "
                "payload when something goes wrong."
            ),
            args_model=_AutoPRCreateArgs,
            handler=_auto_pr_create_handler,
        ),
    ]
