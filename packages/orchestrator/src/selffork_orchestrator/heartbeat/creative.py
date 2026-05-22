"""Creative mode (Yaratma) — Lab workspace + 3-tier scope gate (S-Auto Faz F).

ADR-008 §5.2/5.3 Yaratma mode: when the operator opts in (Settings
toggle ON, default OFF pre-M7), the ``IDEATE`` action records an idea
to the ``Lab`` workspace at ``~/.selffork/lab/ideas/``. Pre-M7 default
behaviour is ``Sadece-fikir`` (operator decision, ADR-008 §11 #4) —
ideas are *recorded only*, never auto-coded; M7 + Settings raise the
ceiling.

3-tier scope gate (ADR-008 §5.3, B*C mix):

* **küçük (small)** — silent record, no operator interrupt.
* **orta (medium)** — record + Telegram notify ("Self Jr started X").
* **büyük (large)** — record + Telegram veto window (4h, **fail-safe
  GO** — sessizlik = devam; ADR-008 §5.4 explicitly opposite of the
  destructive ``NO`` gate).

Faz F implements the **classification + recording**; the Telegram
notify + veto-window persistence (medium / large action steps) wire in
through the executor's existing Telegram bridge — actual auto-coding
of a "promoted" idea happens later (post-M7 / S6 router-aware sprint),
so the 3-tier ceiling is *expressed* but the only behaviour available
in Faz F is "sadece-fikir" (idea recording).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final
from uuid import uuid4

__all__ = [
    "DEFAULT_LAB_ROOT",
    "DEFAULT_LARGE_KEYWORDS",
    "DEFAULT_LARGE_WORD_COUNT",
    "DEFAULT_MEDIUM_WORD_COUNT",
    "CreativeScopeGate",
    "IdeaRecord",
    "IdeaSize",
    "IdeationManager",
    "default_lab_root",
]


_log = logging.getLogger(__name__)


DEFAULT_LAB_ROOT: Final[str] = "~/.selffork/lab/ideas"
"""Default disk location for recorded ideas (Markdown files)."""


DEFAULT_MEDIUM_WORD_COUNT: Final[int] = 60
"""Word-count threshold separating ``small`` from ``medium`` ideas.

The model's reasoning string is the input — short notes ("buton
yenile") stay ``small``; multi-sentence proposals tip into ``medium``.
"""

DEFAULT_LARGE_WORD_COUNT: Final[int] = 180
"""Word-count threshold separating ``medium`` from ``large`` ideas."""


DEFAULT_LARGE_KEYWORDS: Final[tuple[str, ...]] = (
    # Words that imply a heavy commitment regardless of how concise
    # the model phrased the proposal — automatic ``large`` classification.
    "yeni proje",
    "new project",
    "rewrite",
    "refactor entirely",
    "tüm sistemi",
    "from scratch",
    "complete overhaul",
    "migration",
    "infrastructure",
)


def default_lab_root() -> Path:
    """Expanded default Lab workspace root."""
    return Path(DEFAULT_LAB_ROOT).expanduser()


class IdeaSize(StrEnum):
    """3-tier scope per ADR-008 §5.3 (B*C mix; kademeli * kapı label).

    Each tier maps to a different Heartbeat side-effect ceiling:

    * ``small`` — silent record.
    * ``medium`` — record + Telegram notify.
    * ``large`` — record + Telegram veto window (4h, fail-safe GO).
    """

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


@dataclass(frozen=True, slots=True)
class IdeaRecord:
    """One recorded idea — what landed on disk + the classification."""

    idea_id: str
    title: str
    body: str
    size: IdeaSize
    project_slug: str | None
    path: Path
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


class CreativeScopeGate:
    """Deterministic idea-size classifier (ADR-008 §7 Lock #3 + #4).

    Pure function over the model's reasoning text — the gate is
    **kod'da, modelde değil**: a model cannot talk itself out of a
    ``large`` classification by claiming the work is small.

    Rules (any one triggers an upgrade; final size is the strictest):

    1. Word count > ``large_word_count`` → ``large``.
    2. Any ``large_keywords`` substring present → ``large``.
    3. Word count > ``medium_word_count`` → ``medium`` (unless already
       larger).
    4. Otherwise → ``small``.
    """

    def __init__(
        self,
        *,
        medium_word_count: int = DEFAULT_MEDIUM_WORD_COUNT,
        large_word_count: int = DEFAULT_LARGE_WORD_COUNT,
        large_keywords: tuple[str, ...] = DEFAULT_LARGE_KEYWORDS,
    ) -> None:
        if medium_word_count <= 0 or large_word_count <= 0:
            msg = "word-count thresholds must be positive"
            raise ValueError(msg)
        if large_word_count <= medium_word_count:
            msg = "large_word_count must exceed medium_word_count"
            raise ValueError(msg)
        self._medium = medium_word_count
        self._large = large_word_count
        self._keywords = tuple(k.lower() for k in large_keywords)

    def classify(self, idea_text: str) -> IdeaSize:
        text = idea_text.strip().lower()
        if not text:
            return IdeaSize.SMALL

        # Keyword scan first — catches "new project" even when phrased
        # tersely. ``re.search`` is used to honour word boundaries
        # loosely (substring matches are accepted, but the keywords
        # themselves are multi-word so the loose match is reasonable).
        if any(k in text for k in self._keywords):
            return IdeaSize.LARGE

        word_count = len(_WORD_RE.findall(text))
        if word_count > self._large:
            return IdeaSize.LARGE
        if word_count > self._medium:
            return IdeaSize.MEDIUM
        return IdeaSize.SMALL


_WORD_RE: Final[re.Pattern[str]] = re.compile(r"\w+", re.UNICODE)


class IdeationManager:
    """Persist ideas to the Lab workspace as Markdown files.

    Each idea lands at
    ``<lab_root>/<YYYY-MM-DD>-<size>-<idea_id>.md`` so the operator's
    morning review can scan by date + size. The file format is
    deliberately tiny + human-editable — operators can promote an
    idea to a real project task by hand (or, post-M7, the Heartbeat
    promotes it).
    """

    def __init__(
        self,
        *,
        lab_root: Path | None = None,
        scope_gate: CreativeScopeGate | None = None,
    ) -> None:
        self._root = lab_root or default_lab_root()
        self._gate = scope_gate or CreativeScopeGate()

    @property
    def lab_root(self) -> Path:
        return self._root

    def record_idea(
        self,
        *,
        text: str,
        project_slug: str | None = None,
    ) -> IdeaRecord:
        """Persist ``text`` as an idea + return the resulting record."""
        size = self._gate.classify(text)
        idea_id = uuid4().hex[:12]
        title = _derive_title(text)
        created_at = datetime.now(tz=UTC)
        filename = (
            f"{created_at.strftime('%Y-%m-%d')}-{size.value}-{idea_id}.md"
        )
        path = self._root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        body = _render_idea_markdown(
            idea_id=idea_id,
            title=title,
            text=text,
            size=size,
            project_slug=project_slug,
            created_at=created_at,
        )
        path.write_text(body, encoding="utf-8")
        _log.info(
            "heartbeat_idea_recorded",
            extra={
                "idea_id": idea_id,
                "size": size.value,
                "project_slug": project_slug,
                "path": str(path),
            },
        )
        return IdeaRecord(
            idea_id=idea_id,
            title=title,
            body=text,
            size=size,
            project_slug=project_slug,
            path=path,
            created_at=created_at,
        )

    def list_ideas(self) -> list[Path]:
        """Return Markdown files in the lab root, newest first."""
        if not self._root.is_dir():
            return []
        return sorted(
            self._root.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )


def _derive_title(text: str) -> str:
    """First non-empty line, capped at 80 characters."""
    for line in text.splitlines():
        clean = line.strip()
        if clean:
            return clean[:80]
    return "Self Jr idea"


def _render_idea_markdown(
    *,
    idea_id: str,
    title: str,
    text: str,
    size: IdeaSize,
    project_slug: str | None,
    created_at: datetime,
) -> str:
    return (
        f"# {title}\n\n"
        f"- **idea_id:** `{idea_id}`\n"
        f"- **size:** `{size.value}`\n"
        f"- **project:** `{project_slug or '(global)'}`\n"
        f"- **created_at:** `{created_at.isoformat()}`\n"
        f"- **status:** spark\n\n"
        f"---\n\n"
        f"{text.strip()}\n"
    )
