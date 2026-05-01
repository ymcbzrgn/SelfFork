"""Safe shell quoting for CLI args that may contain shell metacharacters.

Wraps :mod:`shlex` so callers don't have to import it directly, and so we
have one obvious place to add SelfFork-specific quoting if a shell quirk
ever forces us off stdlib.

Targets the zsh-glob crash reported when launching CLI agents with model
IDs like ``claude-opus-4-7[1m]`` — brackets are zsh globs unless quoted.
Pattern from `prior art in the agentic-CLI orchestration space`.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §13.
"""

from __future__ import annotations

import shlex
from collections.abc import Iterable

__all__ = ["quote", "quote_argv"]


def quote(value: str) -> str:
    """Quote a single string for safe POSIX-shell consumption.

    Round-trip guarantee: ``sh -c 'echo {quote(value)}'`` echoes ``value``
    with no glob, variable, or command-substitution expansion.
    """
    return shlex.quote(value)


def quote_argv(argv: Iterable[str]) -> str:
    """Join an iterable of args into a single shell-safe command string."""
    return shlex.join(list(argv))
