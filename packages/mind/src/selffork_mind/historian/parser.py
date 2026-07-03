"""Deterministic markdown parser for the Mind historian.

Turns each decision document (``docs/decisions/*.md`` plus the optional
archive) into a :class:`~selffork_mind.historian.model.Decision`, capturing the
file path and the 1-indexed line of every heading so recall can emit a
``path:line`` citation. Pure regex / line-walking -- no embeddings, no markdown
library, no third-party dependency.

Parsing rules (robust to the two real ADR title styles -- ``# ADR-008 -- Title``
and ``# ADR-002: Title`` -- and to the Turkish archive's ``# N. ...`` decision
headings):

- ATX headings (``#``..``######`` at column 0) delimit sections. Fenced code
  blocks (triple backtick / tilde) are skipped so a ``#`` inside a fence is
  never mistaken for a heading.
- The first heading is the document title; its id is the ``ADR-<n>`` token in
  the title when present, else the file stem.
- ``Status:`` / ``**Status:**`` in the metadata region yields the status
  string; the first ``YYYY-MM-DD`` inside it is the decision date (used by the
  continuity digest).
- A malformed file (unreadable, empty, or heading-less) is skipped, never
  raised, so one bad doc cannot break indexing.

The tokenizer is unicode-aware, so Turkish and English text score identically.
"""

from __future__ import annotations

import re
from pathlib import Path

from selffork_mind.historian.model import Decision, DecisionSection

__all__ = [
    "STOPWORDS",
    "index_decisions",
    "tokenize",
]

# ATX heading at column 0: 1-6 hashes, whitespace, text, optional closing hashes.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
# Fenced code-block delimiter (``` or ~~~), possibly indented / info-stringed.
_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
# ADR id token anywhere in the title line.
_ADR_ID_RE = re.compile(r"\bADR-\d+\b", re.IGNORECASE)
# ``Status:`` / ``- **Status:**`` metadata line -> capture the trailing value.
_STATUS_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?status(?:\*\*)?\s*:?\**\s*(.+?)\s*$",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Unicode word run, excluding underscore so ``group_id`` -> ``group``, ``id``.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Lines that never carry a document summary sentence.
_SUMMARY_SKIP_PREFIXES = ("#", "-", "*", "|", ">", "`", "=", "+")
# How many leading lines to scan for the ``Status:`` metadata line.
_STATUS_SCAN_LINES = 60
# Maximum summary length in characters.
_SUMMARY_MAX = 300

# Generic English + Turkish connectors / question words. Domain words such as
# ``karar`` (decision) are deliberately NOT here -- they carry recall signal.
STOPWORDS: frozenset[str] = frozenset(
    {
        # English
        "a", "an", "the", "of", "to", "and", "or", "for", "in", "on", "at",
        "by", "is", "are", "was", "were", "be", "been", "we", "our", "us",
        "did", "do", "does", "what", "which", "how", "why", "when", "about",
        "with", "as", "that", "this", "it", "from",
        # Turkish
        "ve", "ile", "için", "bir", "bu", "şu", "da", "de", "mi", "mu", "mı",
        "ne", "nedir", "nasıl", "hakkında", "ya", "ki",
    }
)


def tokenize(text: str) -> list[str]:
    """Lower-cased unicode word tokens (Turkish + English aware).

    Splits on any non-word character (and underscore), lower-cases, drops
    empties. Deterministic: same input always yields the same token list.
    """
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


def index_decisions(
    decisions_dir: Path,
    *,
    archive: Path | None = None,
) -> list[Decision]:
    """Parse every ``*.md`` under ``decisions_dir`` (+ optional ``archive``).

    Returns one :class:`Decision` per parseable document, in a deterministic
    order (sorted decision-dir files first, then the archive). A missing
    directory yields ``[]``; an unreadable / empty / heading-less file is
    skipped rather than raised.
    """
    files: list[Path] = []
    if decisions_dir.is_dir():
        files.extend(sorted(decisions_dir.glob("*.md")))
    if archive is not None and archive.is_file():
        files.append(archive)

    decisions: list[Decision] = []
    for path in files:
        decision = _parse_file(path)
        if decision is not None:
            decisions.append(decision)
    return decisions


def _parse_file(path: Path) -> Decision | None:
    """Parse one markdown file into a :class:`Decision`, or ``None`` if unusable."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    lines = text.splitlines()
    headings = _find_headings(lines)
    if not headings:
        return None

    title_line, _title_level, title_text = headings[0]
    status, date = _extract_status(lines)
    summary = _extract_summary(lines, title_line)
    sections = _build_sections(lines, headings)

    keywords: set[str] = set()
    for section in sections:
        keywords |= section.keywords
    if status:
        keywords |= set(tokenize(status))

    return Decision(
        id=_extract_id(title_text, path),
        title=title_text,
        path=_relativize(path),
        line=title_line,
        status=status,
        date=date,
        summary=summary,
        sections=tuple(sections),
        keywords=frozenset(keywords),
    )


def _find_headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """Return ``(line_1indexed, level, heading_text)`` for every ATX heading.

    Lines inside fenced code blocks are ignored.
    """
    headings: list[tuple[int, int, str]] = []
    in_fence = False
    for index, raw in enumerate(lines):
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(raw)
        if match is not None:
            headings.append((index + 1, len(match.group(1)), match.group(2).strip()))
    return headings


def _build_sections(
    lines: list[str],
    headings: list[tuple[int, int, str]],
) -> list[DecisionSection]:
    """Build one :class:`DecisionSection` per heading, body = until next heading."""
    sections: list[DecisionSection] = []
    for position, (line_no, level, heading_text) in enumerate(headings):
        body_start = line_no  # 0-indexed line just after the heading.
        is_last = position + 1 >= len(headings)
        body_end = len(lines) if is_last else headings[position + 1][0] - 1
        body = "\n".join(lines[body_start:body_end])
        keywords = frozenset(tokenize(heading_text)) | frozenset(tokenize(body))
        sections.append(
            DecisionSection(
                heading=heading_text,
                line=line_no,
                level=level,
                keywords=keywords,
            )
        )
    return sections


def _extract_id(title_text: str, path: Path) -> str:
    """ADR id from the title (upper-cased) or the file stem as a fallback."""
    match = _ADR_ID_RE.search(title_text)
    if match is not None:
        return match.group(0).upper()
    return path.stem


def _extract_status(lines: list[str]) -> tuple[str | None, str | None]:
    """First ``Status:`` value in the metadata region, plus its first date."""
    for raw in lines[:_STATUS_SCAN_LINES]:
        match = _STATUS_RE.match(raw)
        if match is None:
            continue
        status = match.group(1).strip()
        if not status:
            continue
        date_match = _DATE_RE.search(status)
        return status, (date_match.group(0) if date_match is not None else None)
    return None, None


def _extract_summary(lines: list[str], title_line: int) -> str:
    """First prose paragraph after the title, metadata / heading lines skipped."""
    collected: list[str] = []
    started = False
    for raw in lines[title_line:]:
        stripped = raw.strip()
        if not stripped:
            if started:
                break
            continue
        if stripped.startswith(_SUMMARY_SKIP_PREFIXES):
            if started:
                break
            continue
        collected.append(stripped)
        started = True
        if sum(len(part) + 1 for part in collected) > _SUMMARY_MAX:
            break
    return " ".join(collected)[:_SUMMARY_MAX].strip()


def _relativize(path: Path) -> str:
    """Posix citation path -- relative to the cwd when the file lives under it.

    Tools run from the repo root, so decision docs resolve to
    ``docs/decisions/ADR-...md``; files elsewhere (e.g. pytest ``tmp_path``)
    fall back to their absolute posix path.
    """
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()
