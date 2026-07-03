"""Mind historian -- deterministic decision recall with ``path:line`` citation.

Per PRD 8.3.4 + ADR-002 (historian): index the project's decision docs
(``docs/decisions/*.md`` + the ``docs/archive`` ledger) into a queryable
structure, answer "what did we decide about X?" with the matching decision(s),
and return a ``path:line`` citation for each. Fully deterministic -- regex /
markdown line-walking, no embeddings, no vector store.

Public surface:

- :func:`index_decisions` -- parse a decisions directory (+ optional archive)
  into :class:`Decision` records, each anchored to a heading line for citation.
- :class:`Historian` -- ``recall(query, top_k=...)`` returns ranked
  :class:`DecisionHit` records whose ``citation`` is ``path:line``;
  ``continuity_summary()`` returns a recent-decisions digest.
- :class:`Decision` / :class:`DecisionSection` / :class:`DecisionHit` -- the
  record types.
- :func:`tokenize` -- the shared unicode (Turkish + English) tokenizer.
"""

from __future__ import annotations

from selffork_mind.historian.model import (
    Decision,
    DecisionHit,
    DecisionSection,
)
from selffork_mind.historian.parser import (
    STOPWORDS,
    index_decisions,
    tokenize,
)
from selffork_mind.historian.recall import Historian

__all__ = [
    "STOPWORDS",
    "Decision",
    "DecisionHit",
    "DecisionSection",
    "Historian",
    "index_decisions",
    "tokenize",
]
