"""Plain-markdown projection of Mind state.

Per ADR-002 §7. Mirrors Claude Code's MEMORY.md + topic-files pattern:

- ``MEMORY.md`` — index, one line per note (link + 1-line description).
  Hard cap configurable (default 200 lines, matches Claude Code).
- ``topics/<note_id>.md`` — full content + frontmatter.

The projection is **deterministic**: same set of notes → same files. We
write atomically (tmp + rename) so concurrent reads never see torn files.

Operators can edit topic files; on next save the editor diff is captured
back into the store. Order 1 ships the writer; the reader (edit→store
sync) lands in Order 2 alongside the CLI.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from selffork_mind.memory.model import Note

__all__ = ["MarkdownProjection", "MarkdownProjectionConfig"]


@dataclass(frozen=True, slots=True)
class MarkdownProjectionConfig:
    """Knobs for the markdown projection."""

    root: Path
    """Output directory; ``MEMORY.md`` + ``topics/`` live here."""

    index_line_cap: int = 200
    """Hard cap on MEMORY.md line count (Claude Code convention)."""

    topic_dir: str = "topics"
    """Subdirectory for per-note topic files."""

    index_filename: str = "MEMORY.md"
    """Filename for the index."""


class MarkdownProjection:
    """Writes a deterministic markdown projection of a set of notes.

    Single-process safe; not multi-writer safe (same root + concurrent
    writers will race). Use one projector per project per process.
    """

    def __init__(self, config: MarkdownProjectionConfig) -> None:
        self._config = config

    @property
    def root(self) -> Path:
        """Output directory; ``MEMORY.md`` + ``topics/`` live here."""
        return self._config.root

    @property
    def index_path(self) -> Path:
        """Absolute path to the ``MEMORY.md`` index file."""
        return self._config.root / self._config.index_filename

    def write(self, notes: list[Note]) -> None:
        """Render the index + topic files for a list of notes.

        Sorts by ``(tier, valid_from desc)``; truncates the index at
        ``index_line_cap`` (older overflow goes only to topic files).
        """
        root = self._config.root
        topic_root = root / self._config.topic_dir
        topic_root.mkdir(parents=True, exist_ok=True)

        # Topic files first — write every note even if it overflows the index.
        for note in notes:
            self._write_topic(topic_root, note)

        # Index — sorted, capped.
        sorted_notes = sorted(
            notes,
            key=lambda n: (n.tier, n.valid_from),
            reverse=True,
        )
        index_lines: list[str] = [
            "# SelfFork Mind — MEMORY.md",
            "",
            "Auto-generated index of Mind state. Topic files live under "
            f"`{self._config.topic_dir}/`. Edit topic files freely; "
            "this index is rewritten on every projection cycle.",
            "",
        ]
        for n in sorted_notes:
            line = self._index_line(n)
            if len(index_lines) + 1 >= self._config.index_line_cap:
                # Stop adding to the index, but topic files are still on disk.
                index_lines.append(
                    f"_…and {len(sorted_notes) - (len(index_lines) - 4)} more "
                    f"in `{self._config.topic_dir}/`._",
                )
                break
            index_lines.append(line)

        self._atomic_write(
            root / self._config.index_filename,
            "\n".join(index_lines) + "\n",
        )

    def _write_topic(self, topic_root: Path, note: Note) -> None:
        path = topic_root / f"{note.id}.md"
        body = self._render_topic(note)
        self._atomic_write(path, body)

    @staticmethod
    def _render_topic(note: Note) -> str:
        frontmatter_dict = {
            "id": str(note.id),
            "tier": note.tier,
            "kind": note.kind,
            "intent": note.intent,
            "valid_from": note.valid_from.isoformat(),
            "valid_until": (note.valid_until.isoformat() if note.valid_until is not None else None),
            "project_slug": note.project_slug,
            "session_id": note.session_id,
            "source_pointer": note.source_pointer,
            "path_scope": list(note.path_scope),
            "always_apply": note.always_apply,
            "importance": note.importance,
            "pinned": note.pinned,
            "tag_keys": list(note.tag_keys),
        }
        # JSON frontmatter — unambiguous, machine-readable, and (unlike YAML)
        # has a single canonical serialisation so the file diff is stable.
        frontmatter = json.dumps(frontmatter_dict, indent=2, ensure_ascii=False)
        return (
            "---json\n"
            f"{frontmatter}\n"
            "---\n"
            "\n"
            f"# {note.intent or note.kind.title()}\n"
            "\n"
            f"{note.content}\n"
        )

    @staticmethod
    def _index_line(note: Note) -> str:
        title = note.intent or note.content.splitlines()[0][:80]
        descriptor = f"[{note.tier}]"
        if note.pinned:
            descriptor += " [pinned]"
        return f"- [{title}](topics/{note.id}.md) {descriptor}"

    @staticmethod
    def _atomic_write(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_name, target)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise

    def topic_path_for(self, note_id: UUID) -> Path:
        """Return the on-disk path for a note's topic file."""
        return self._config.root / self._config.topic_dir / f"{note_id}.md"
