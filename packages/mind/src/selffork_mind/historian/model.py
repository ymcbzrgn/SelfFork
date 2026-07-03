"""Data model for the Mind historian -- deterministic decision recall.

Per PRD 8.3.4 + ADR-002 (historian): decision recall with a ``path:line``
citation. These records are produced by
:mod:`selffork_mind.historian.parser` from the project's decision docs
(``docs/decisions/*.md`` + the optional archive) and consumed by
:class:`selffork_mind.historian.recall.Historian`.

- :class:`DecisionSection` -- one heading-anchored region inside a decision
  document. Carries the heading text, its 1-indexed source line (the citation
  anchor), the heading depth, and the pre-tokenized keyword set used for
  deterministic scoring.
- :class:`Decision` -- one decision document (an ADR file or the archive).
  Aggregates its title, parsed status/date, a short summary, and the ordered
  :class:`DecisionSection` list. ``path``/``line`` form the default
  ``path:line`` citation (the title heading).
- :class:`DecisionHit` -- a scored recall result. Points at the matched
  heading (which may be a sub-section, not the title), so ``citation`` cites
  the most relevant line, e.g. ``docs/decisions/ADR-008_...md:264``.

No embeddings, no I/O here -- pure frozen dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "Decision",
    "DecisionHit",
    "DecisionSection",
]


@dataclass(frozen=True, slots=True)
class DecisionSection:
    """A heading-anchored region of a decision document.

    ``line`` is 1-indexed and points at the heading line -- it is the anchor a
    citation resolves to. ``keywords`` are the lower-cased tokens of the
    heading plus its body text, pre-computed so scoring stays allocation-cheap.
    """

    heading: str
    line: int
    level: int
    keywords: frozenset[str]


@dataclass(frozen=True, slots=True)
class Decision:
    """One decision document parsed from markdown.

    ``id`` is the ADR id (e.g. ``ADR-008``) when the title carries one, else
    the file stem. ``path`` is the citation path (posix, repo-root-relative
    when the file lives under the cwd) and ``line`` is the 1-indexed line of
    the title heading, so :attr:`citation` yields e.g.
    ``docs/decisions/ADR-008_Autonomy_Heartbeat.md:1``.

    ``status`` / ``date`` are parsed from the document's ``Status:`` line when
    present (``None`` otherwise). ``keywords`` is the union of every section's
    tokens plus the status tokens -- the fast-membership set used for
    document-level scoring.
    """

    id: str
    title: str
    path: str
    line: int
    status: str | None
    date: str | None
    summary: str
    sections: tuple[DecisionSection, ...]
    keywords: frozenset[str]

    @property
    def citation(self) -> str:
        """``path:line`` pointing at the document's title heading."""
        return f"{self.path}:{self.line}"


@dataclass(frozen=True, slots=True)
class DecisionHit:
    """A scored recall result with a resolved ``path:line`` citation.

    ``line`` and ``matched_heading`` identify the most relevant heading inside
    :attr:`decision` for the query -- the document title by default, or a
    sub-section when one scores higher. ``score`` is the deterministic keyword
    overlap score (higher is better); it is not normalised across queries.
    """

    decision: Decision
    score: float
    line: int
    matched_heading: str

    @property
    def citation(self) -> str:
        """``path:line`` pointing at the matched heading."""
        return f"{self.decision.path}:{self.line}"
