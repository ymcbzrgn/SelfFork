"""Deterministic decision recall for the Mind historian.

:class:`Historian` indexes the project's decision docs (via
:func:`~selffork_mind.historian.parser.index_decisions`) and answers
"what did we decide about X?" with the matching
:class:`~selffork_mind.historian.model.Decision` records, each carrying a
``path:line`` citation that points at the most relevant heading.

Scoring is pure keyword overlap -- title / heading / body weighted, Turkish +
English via the shared unicode tokenizer. It is embedding-free and fully
deterministic: the same query always returns the same ranked hits, and ties
break on the decision id then the cited line so ordering is stable.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from selffork_mind.historian.model import Decision, DecisionHit
from selffork_mind.historian.parser import STOPWORDS, index_decisions, tokenize

__all__ = ["Historian"]

# Field weights: a query term is worth more when it hits the title than the
# body. Each query term contributes the single best field it appears in.
_TITLE_WEIGHT = 3.0
_HEADING_WEIGHT = 2.0
_BODY_WEIGHT = 1.0
# Boost when the query names a decision id outright, e.g. "what about ADR-009".
_ID_MATCH_BOOST = 5.0
# Section-selection weights (which heading a citation points at).
_SECTION_HEADING_WEIGHT = 2.0
_SECTION_BODY_WEIGHT = 1.0
# Continuity-digest clip lengths.
_TITLE_CLIP = 72
_STATUS_CLIP = 48


class Historian:
    """Deterministic decision recall over indexed decision documents."""

    def __init__(self, decisions: Sequence[Decision]) -> None:
        self._decisions: tuple[Decision, ...] = tuple(decisions)

    @classmethod
    def from_dir(
        cls,
        decisions_dir: Path,
        *,
        archive: Path | None = None,
    ) -> Historian:
        """Build a historian by indexing ``decisions_dir`` (+ optional archive)."""
        return cls(index_decisions(decisions_dir, archive=archive))

    @property
    def decisions(self) -> tuple[Decision, ...]:
        """The indexed decisions, in deterministic index order."""
        return self._decisions

    def recall(self, query: str, *, top_k: int = 3) -> list[DecisionHit]:
        """Return up to ``top_k`` decisions matching ``query``, best first.

        Each hit's :attr:`~selffork_mind.historian.model.DecisionHit.citation`
        points at the most relevant heading -- the document title by default,
        or a sub-section when one scores higher. An empty / whitespace query,
        ``top_k <= 0``, or no match yields ``[]``.
        """
        if top_k <= 0:
            return []
        if not query.strip():
            return []

        query_tokens = frozenset(t for t in tokenize(query) if t not in STOPWORDS)
        query_norm = query.strip().lower()

        hits: list[DecisionHit] = []
        for decision in self._decisions:
            score = _score_decision(decision, query_tokens, query_norm)
            if score <= 0.0:
                continue
            line, heading = _best_section(decision, query_tokens)
            hits.append(
                DecisionHit(
                    decision=decision,
                    score=score,
                    line=line,
                    matched_heading=heading,
                )
            )

        hits.sort(key=lambda hit: (-hit.score, hit.decision.id, hit.line))
        return hits[:top_k]

    def continuity_summary(self, *, limit: int = 5) -> str:
        """A short digest of the most recent decisions, each with its citation.

        Recency is by parsed decision date (descending), then id (descending)
        so undated / lower-numbered decisions sort last. Returns a fixed
        placeholder line when there is nothing to report.
        """
        if limit <= 0 or not self._decisions:
            return "No decisions on record."

        recent = sorted(
            self._decisions,
            key=lambda decision: (decision.date or "", decision.id),
            reverse=True,
        )[:limit]

        rows = ["Recent decisions:"]
        for decision in recent:
            date = decision.date or "no date"
            status = _clip(decision.status or "unknown status", _STATUS_CLIP)
            title = _clip(decision.title, _TITLE_CLIP)
            rows.append(
                f"- [{decision.id}] {title} ({date}, {status}) -- {decision.citation}"
            )
        return "\n".join(rows)


def _score_decision(
    decision: Decision,
    query_tokens: frozenset[str],
    query_norm: str,
) -> float:
    """Weighted keyword-overlap score for one decision against the query."""
    score = 0.0
    if query_tokens:
        title_tokens = frozenset(tokenize(decision.title))
        heading_tokens = _heading_tokens(decision)
        for token in query_tokens:
            if token in title_tokens:
                score += _TITLE_WEIGHT
            elif token in heading_tokens:
                score += _HEADING_WEIGHT
            elif token in decision.keywords:
                score += _BODY_WEIGHT
    if decision.id.lower() in query_norm:
        score += _ID_MATCH_BOOST
    return score


def _heading_tokens(decision: Decision) -> frozenset[str]:
    """Union of tokens across every section heading (title included)."""
    tokens: set[str] = set()
    for section in decision.sections:
        tokens.update(tokenize(section.heading))
    return frozenset(tokens)


def _best_section(decision: Decision, query_tokens: frozenset[str]) -> tuple[int, str]:
    """Pick the heading whose section best matches the query.

    Returns ``(line, heading)``. Heading-token overlap counts double body
    overlap. Ties prefer the earliest (smallest-line) heading, so the document
    title wins when nothing more specific matches -- yielding a ``...:1``
    citation in the common case.
    """
    best_line = decision.line
    best_heading = decision.title
    best_score = -1.0
    for section in decision.sections:
        heading_tokens = frozenset(tokenize(section.heading))
        section_score = (
            _SECTION_HEADING_WEIGHT * len(query_tokens & heading_tokens)
            + _SECTION_BODY_WEIGHT * len(query_tokens & section.keywords)
        )
        if section_score > best_score or (
            section_score == best_score and section.line < best_line
        ):
            best_score = section_score
            best_line = section.line
            best_heading = section.heading
    return best_line, best_heading


def _clip(text: str, limit: int) -> str:
    """Collapse whitespace and truncate ``text`` to ``limit`` characters."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: max(limit - 3, 0)].rstrip() + "..."
