"""Backend → implementation resolver for :class:`LimitDetector`.

Maps a CLI agent name to its rate-limit detector. Mirrors
:func:`selffork_orchestrator.cli_agent.factory.build_cli_agent`.
"""

from __future__ import annotations

from collections.abc import Mapping

from selffork_orchestrator.limits.base import LimitDetector
from selffork_orchestrator.limits.claude_detector import ClaudeRateLimitDetector
from selffork_orchestrator.limits.gemini_detector import GeminiRateLimitDetector
from selffork_orchestrator.limits.opencode_detector import OpenCodeRateLimitDetector

__all__ = ["build_limit_detector"]

_DETECTORS: Mapping[str, type[LimitDetector]] = {
    "opencode": OpenCodeRateLimitDetector,
    "claude-code": ClaudeRateLimitDetector,
    "gemini-cli": GeminiRateLimitDetector,
    # codex is still a stubbed CLI agent (M2-M3); when it ships, give it
    # its own detector here.
}


def build_limit_detector(cli_agent_name: str) -> LimitDetector:
    """Return a fresh :class:`LimitDetector` for ``cli_agent_name``.

    Raises:
        ValueError: when no detector is registered for the agent name.
            This is a programming error — the caller should have
            validated against ``CLIAgentConfig.agent`` first.
    """
    cls = _DETECTORS.get(cli_agent_name)
    if cls is None:
        raise ValueError(
            f"no rate-limit detector for cli agent {cli_agent_name!r}; known: {sorted(_DETECTORS)}",
        )
    return cls()
