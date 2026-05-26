"""Skills tool pack — SkillInstaller wrap (~10 tools, all deferred).

S-ToolFleet Faz 3. Operator-level skill lifecycle ops on top of
:class:`selffork_orchestrator.skills.SkillInstaller`. Tools wrap:
list / show / sync / install / uninstall / update / search / validate /
export / create.

Reference: SelfFork Hivemind H4 pattern lift ([[hivemind-adoption]])
— canonical ``~/.selffork/skills/`` source-of-truth + symlink fan-out
to four wired CLI agents (claude-code / codex / gemini-cli / opencode).

All deferred — operator dev-time tooling, not part of the agentic loop.
"""

from __future__ import annotations

from typing import Any

from selffork_orchestrator.tools.base import ToolSpec
from selffork_orchestrator.tools.skills.tools import build_skills_tools_inner

__all__ = ["build_skills_tools"]


def build_skills_tools() -> list[ToolSpec[Any]]:
    return build_skills_tools_inner()
