"""Build :class:`Snapper` instances by CLI agent name.

Mirrors :func:`selffork_orchestrator.cli_agent.factory.build_cli_agent` and
:func:`selffork_orchestrator.limits.factory.build_limit_detector`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from selffork_orchestrator.snappers.base import Snapper
from selffork_orchestrator.snappers.claude import ClaudeSnapper
from selffork_orchestrator.snappers.codex import CodexSnapper
from selffork_orchestrator.snappers.gemini import GeminiSnapper
from selffork_orchestrator.snappers.minimax import MinimaxSnapper
from selffork_orchestrator.snappers.opencode import OpenCodeSnapper
from selffork_orchestrator.snappers.zai import ZaiSnapper

__all__ = ["build_default_snappers", "build_snapper", "registered_snapper_ids"]

# ``zai`` is a snapper-only entry: Z.AI is an opencode-routed provider,
# not a standalone CLI agent. The snapper exposes its OAuth subscription
# state without claiming a CLIAgentConfig literal.
#
# Type is ``Callable[[], Snapper]`` (not ``type[Snapper]``) because each
# concrete subclass overrides ``__init__`` with its own keyword-only
# defaults — calling ``cls()`` is type-safe per Python semantics, but
# mypy needs the protocol-style annotation to allow it.
_SNAPPERS: Mapping[str, Callable[[], Snapper]] = {
    "claude-code": ClaudeSnapper,
    "codex": CodexSnapper,
    "gemini-cli": GeminiSnapper,
    "opencode": OpenCodeSnapper,
    "minimax-cli": MinimaxSnapper,
    "zai": ZaiSnapper,
}


def registered_snapper_ids() -> tuple[str, ...]:
    """Return the tuple of CLI IDs with a registered snapper class."""
    return tuple(sorted(_SNAPPERS))


def build_snapper(cli_agent_name: str) -> Snapper:
    """Return a fresh :class:`Snapper` for ``cli_agent_name``.

    Raises:
        ValueError: when no snapper is registered for ``cli_agent_name``.
            This is a programming error — the caller should have validated
            against the registry first.
    """
    cls = _SNAPPERS.get(cli_agent_name)
    if cls is None:
        raise ValueError(
            f"no snapper for cli agent {cli_agent_name!r}; known: {sorted(_SNAPPERS)}",
        )
    return cls()


def build_default_snappers() -> list[Snapper]:
    """Return one snapper per registered CLI agent (default config).

    Use this for the canonical fleet that runs alongside the orchestrator.
    """
    return [cls() for cls in _SNAPPERS.values()]
