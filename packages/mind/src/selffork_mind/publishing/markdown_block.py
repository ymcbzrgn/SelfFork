"""Idempotent BEGIN/END marker publishing for repo-root agent files.

Per ADR-009 §9 ("AGENTS.md BEGIN/END idempotent marker", Hivemind H3 lift)
and ADR-002 §13 ("AGENTS.md publishing"). SelfFork upserts a small
"Mind Access" instructions block into the repo-root agent files so that
external CLIs (Codex, Cursor, opencode, gemini-cli, Claude Code via
``@import``) discover how to reach SelfFork's Mind.

This module is a self-contained, pure string-manipulation library. It does
NOT touch the store, LanceDB, or a live app -- the operator (or a CLI
command) calls it with an explicit ``root`` and an already-rendered block.

Marker sentinels (ADR-009 §9, verbatim):

    <!-- BEGIN selffork-mind -->
    ...block content...
    <!-- END selffork-mind -->

Idempotency contract:

- :func:`upsert_block` inserts the delimited block if absent, or replaces
  the existing delimited region in place if present. Running it twice with
  the same ``block`` argument yields byte-identical output.
- :func:`strip_block` removes the delimited region (and its blank-line
  separator) if present, and is a no-op if absent.

Malformed / half-present markers (only a BEGIN with no matching END, or an
orphan END) are treated as ordinary text: the whole-region regex requires
BOTH sentinels, so a half marker never matches. :func:`upsert_block` then
appends a fresh, well-formed block and leaves the stray sentinel untouched;
:func:`strip_block` leaves it untouched too. This is deliberate -- guessing
where a broken region ends risks deleting operator content, so we never do.

Note on naming: ADR-009 §9 names the Hivemind lift ``upsertSelffokBlock`` /
``stripSelffokBlock`` (JS camelCase, and a typo for "selffork"). We expose
idiomatic Python ``upsert_block`` / ``strip_block`` instead; the sentinel
strings themselves match the ADR verbatim.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from pathlib import Path

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

# Marker sentinels -- ADR-009 §9 verbatim. HTML comments so the block is
# invisible when the markdown is rendered, yet trivially machine-locatable.
BEGIN_MARKER = "<!-- BEGIN selffork-mind -->"
END_MARKER = "<!-- END selffork-mind -->"

# Repo-root agent files, in publish order. AGENTS.md is the cross-tool
# Linux Foundation standard (Codex/Cursor/opencode); CLAUDE.md and GEMINI.md
# are the Anthropic / Google conventions; AGENT.md is the opencode singular
# alias. See ADR-009 §9 and ADR-002 §13.
DEFAULT_AGENT_FILENAMES: tuple[str, ...] = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "AGENT.md",
)

# Canonical Mind-access block content (ADR-009 §9, verbatim, WITHOUT the
# BEGIN/END sentinels -- those are added by the renderer). Exposed so callers
# and CLIs share one source of truth; ``publish_mind_block`` still takes the
# block explicitly so operators can override it.
DEFAULT_MIND_BLOCK = (
    "## SelfFork Mind Access\n"
    "\n"
    "Use `mind_recall(query, scope)` and `mind_note_add(...)` for memory operations.\n"
    "\n"
    "- PROJECT pool: this project's notes/decisions/codebase patterns\n"
    "- GLOBAL pool: operator preferences and cross-project lessons\n"
    "\n"
    "Plain-md projections:\n"
    "- ~/.selffork/projects/<slug>/mind/markdown/\n"
    "- ~/.selffork/global/mind/markdown/\n"
    "\n"
    "Tools: mind_recall (with PoolScope), mind_note_add, mind_compact."
)


def _block_pattern(begin: str, end: str) -> re.Pattern[str]:
    """Compile a non-greedy regex matching a full ``begin``..``end`` region.

    Requires BOTH sentinels; ``.*?`` with ``DOTALL`` spans intervening lines
    but stops at the first ``end`` so adjacent blocks are not merged.
    """
    return re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)


def _render_block(block: str, *, begin: str, end: str) -> str:
    """Render the delimited region: sentinel, body, sentinel.

    The body is stripped of leading/trailing newlines so the render is
    deterministic regardless of how the caller pads ``block``.
    """
    body = block.strip("\n")
    if not body:
        return f"{begin}\n{end}"
    return f"{begin}\n{body}\n{end}"


def _append_block(text: str, rendered: str) -> str:
    """Append ``rendered`` to ``text`` with a single blank-line separator.

    Trailing newlines at EOF are normalized to exactly one blank line; all
    other existing content is preserved verbatim.
    """
    base = text.rstrip("\n")
    if not base:
        return rendered + "\n"
    return f"{base}\n\n{rendered}\n"


def upsert_block(
    text: str,
    *,
    block: str,
    begin: str = BEGIN_MARKER,
    end: str = END_MARKER,
) -> str:
    """Insert or replace the delimited block in ``text`` idempotently.

    If a ``begin``..``end`` region exists, its FIRST occurrence is replaced
    in place (position and surrounding text preserved). Otherwise the block
    is appended after a blank-line separator. Running this twice with the
    same ``block`` yields byte-identical output.

    If ``text`` somehow contains multiple full blocks (hand-authored), only
    the first is updated; extras are left untouched -- deleting them could
    drop operator content.
    """
    rendered = _render_block(block, begin=begin, end=end)
    match = _block_pattern(begin, end).search(text)
    if match is None:
        return _append_block(text, rendered)
    return text[: match.start()] + rendered + text[match.end() :]


def strip_block(
    text: str,
    *,
    begin: str = BEGIN_MARKER,
    end: str = END_MARKER,
) -> str:
    """Remove the delimited block (and its blank-line separator) if present.

    Idempotent: a no-op when no full ``begin``..``end`` region exists. The
    regex consumes up to two newlines immediately before ``begin`` (the
    separator :func:`upsert_block` inserts) and the trailing newline of the
    ``end`` line, then the result's EOF is normalized to a single trailing
    newline. For a block appended at EOF this restores the pre-upsert text
    byte-for-byte.
    """
    pattern = re.compile(
        r"\n{0,2}" + re.escape(begin) + r".*?" + re.escape(end),
        re.DOTALL,
    )
    if pattern.search(text) is None:
        return text
    result = pattern.sub("", text)
    result = result.rstrip("\n")
    if result:
        result += "\n"
    return result


def _atomic_write(target: Path, content: str) -> None:
    """Write ``content`` to ``target`` atomically (tmp + rename).

    Mirrors the projections writer: concurrent readers never see a torn
    file. ``newline="\\n"`` keeps output deterministic across platforms.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(tmp_name, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def publish_to_file(
    path: Path,
    block: str,
    *,
    begin: str = BEGIN_MARKER,
    end: str = END_MARKER,
) -> bool:
    """Upsert ``block`` into the file at ``path``; write only if it changed.

    Reads the file (treating a missing file as empty), upserts the block,
    and writes back only when the content differs. Parent directories are
    created if needed. Returns ``True`` if the file was created or modified,
    ``False`` if it was already up to date.
    """
    existed = path.exists()
    original = path.read_text(encoding="utf-8") if existed else ""
    updated = upsert_block(original, block=block, begin=begin, end=end)
    if existed and updated == original:
        return False
    _atomic_write(path, updated)
    return True


def default_agent_files(root: Path) -> list[Path]:
    """Return the repo-root agent files to publish into, in publish order.

    ``root/AGENTS.md``, ``root/CLAUDE.md``, ``root/GEMINI.md``,
    ``root/AGENT.md`` (see :data:`DEFAULT_AGENT_FILENAMES`).
    """
    return [root / name for name in DEFAULT_AGENT_FILENAMES]


def publish_mind_block(
    root: Path,
    block: str,
    *,
    begin: str = BEGIN_MARKER,
    end: str = END_MARKER,
) -> dict[Path, bool]:
    """Publish ``block`` into every default agent file under ``root``.

    Returns a mapping of each target path to whether it was created or
    modified. Idempotent: a second call with the same ``block`` returns all
    ``False``.
    """
    return {
        path: publish_to_file(path, block, begin=begin, end=end)
        for path in default_agent_files(root)
    }
