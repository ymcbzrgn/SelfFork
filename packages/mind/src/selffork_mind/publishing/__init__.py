"""Publishing of the Mind-access instructions block into agent files.

Per ADR-009 §9 and ADR-002 §13. Upserts an idempotent BEGIN/END delimited
block into the repo-root agent files (``AGENTS.md`` / ``CLAUDE.md`` /
``GEMINI.md`` / ``AGENT.md``) so external CLIs discover how to reach the
SelfFork Mind. Pure string manipulation -- no store, no live app.

See :mod:`selffork_mind.publishing.markdown_block` for the implementation.
"""

from __future__ import annotations

from selffork_mind.publishing.markdown_block import (
    BEGIN_MARKER,
    DEFAULT_AGENT_FILENAMES,
    DEFAULT_MIND_BLOCK,
    END_MARKER,
    default_agent_files,
    publish_mind_block,
    publish_to_file,
    strip_block,
    upsert_block,
)

__all__ = [
    "BEGIN_MARKER",
    "DEFAULT_AGENT_FILENAMES",
    "DEFAULT_MIND_BLOCK",
    "END_MARKER",
    "default_agent_files",
    "publish_mind_block",
    "publish_to_file",
    "strip_block",
    "upsert_block",
]
