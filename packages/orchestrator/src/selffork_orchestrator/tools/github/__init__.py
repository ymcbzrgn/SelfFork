"""GitHub tool pack — `gh` CLI subprocess wrappers (~15 tools).

S-ToolFleet Faz 3. PAT-based auth via the user's existing
``~/.config/gh/hosts.yml``; per [[s-vision-candidates-github-rag-2026-05-24]]
operator decision: commit identity = name-only + Gravatar, PAT over App.

Warden-gated through ``_gate`` directly (no body_driver requirement) —
GitHub tools are operator/Self-Jr self-commit ops, not body actions.
Self Jr self-commit flow goes through ``auto_pr_create`` (Faz 0); the
``github_*`` tools cover the wider workflow surface (issues / PR review /
workflows / repo lifecycle).

Eager bucket (3) = ``github_pr_create / github_issue_create /
github_issue_list`` — the agentic-loop core for self-commit + status
checks. Remaining 12 defer behind ``tool_search``.
"""

from __future__ import annotations

from typing import Any

from selffork_orchestrator.tools.base import ToolSpec
from selffork_orchestrator.tools.github.tools import build_github_tools_inner

__all__ = ["build_github_tools"]


def build_github_tools() -> list[ToolSpec[Any]]:
    """Return every github tool in canonical ordering."""
    return build_github_tools_inner()
