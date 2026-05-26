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

__all__ = [
    "build_default_snappers",
    "build_snapper",
    "registered_snapper_ids",
]

# Full snapper registry — every concrete class that can be instantiated
# by name via :func:`build_snapper`. Operators who want explicit per-CLI
# snapshots (e.g. a custom one-shot diagnostic) still reach for these.
#
# Type is ``Callable[[], Snapper]`` (not ``type[Snapper]``) because each
# concrete subclass overrides ``__init__`` with its own keyword-only
# defaults — calling ``cls()`` is type-safe per Python semantics, but
# mypy needs the protocol-style annotation to allow it.
_ALL_SNAPPERS: Mapping[str, Callable[[], Snapper]] = {
    "claude-code": ClaudeSnapper,
    "codex": CodexSnapper,
    "gemini-cli": GeminiSnapper,
    "opencode": OpenCodeSnapper,
    # ``minimax-cli`` + ``zai`` (Z.AI/GLM): operator 2026-05-26 — both
    # are routed via opencode (opencode CLI exposes them as provider
    # routes; their quota lives inside opencode's session usage). Self
    # Jr never invokes them as standalone CLIs, so the default fleet
    # below excludes them. Classes remain reachable here for explicit
    # one-shot use via ``build_snapper(...)``.
    "minimax-cli": MinimaxSnapper,
    "zai": ZaiSnapper,
}

# Default fleet — the CLIs whose snapper actually runs under the
# SnapperRunner sidecar. Mirrors the wired CLI agent set
# (``DEFAULT_CLI_IDS`` in the router): claude-code + codex + gemini-cli
# + opencode. minimax-cli + zai are intentionally absent (see
# :data:`_ALL_SNAPPERS` block comment).
_DEFAULT_SNAPPER_IDS: tuple[str, ...] = (
    "claude-code",
    "codex",
    "gemini-cli",
    "opencode",
)


def registered_snapper_ids() -> tuple[str, ...]:
    """Return the active default-fleet CLI IDs (in declaration order)."""
    return _DEFAULT_SNAPPER_IDS


def build_snapper(cli_agent_name: str) -> Snapper:
    """Return a fresh :class:`Snapper` for ``cli_agent_name``.

    Reaches into the full registry, including the via-opencode entries
    (``minimax-cli``, ``zai``); the default fleet excludes those but
    explicit construction MUST stay available for diagnostics.

    Raises:
        ValueError: when no snapper is registered for ``cli_agent_name``.
            This is a programming error — the caller should have validated
            against the registry first.
    """
    cls = _ALL_SNAPPERS.get(cli_agent_name)
    if cls is None:
        raise ValueError(
            f"no snapper for cli agent {cli_agent_name!r}; "
            f"known: {sorted(_ALL_SNAPPERS)}",
        )
    return cls()


def build_default_snappers() -> list[Snapper]:
    """Return one snapper per active default-fleet CLI.

    Use this for the canonical fleet that runs alongside the
    orchestrator (Heartbeat sidecar + per-session SnapperRunner).
    Includes only the wired CLI agents — minimax-cli + zai (Z.AI/GLM)
    are explicitly excluded because they're routed via opencode and
    their quota lives in opencode's session usage.
    """
    return [_ALL_SNAPPERS[cli_id]() for cli_id in _DEFAULT_SNAPPER_IDS]
