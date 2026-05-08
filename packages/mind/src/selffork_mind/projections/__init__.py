"""User-facing projections of Mind state.

Per ADR-002 §7-§8. The internal store (DuckDB+LanceDB+Kuzu) is the source
of truth, but the operator interacts with two projections:

- :mod:`selffork_mind.projections.markdown` — plain-markdown ``MEMORY.md`` +
  topic files, user-editable. Cursor 2.1 lesson: opacity loses.
- :mod:`selffork_mind.projections.provenance` — every Mind-injected memory
  carries a trace ("this answer used note X from session Y") so the UI can
  surface Sources (ChatGPT Memory Sources May 2026 pattern).
"""

from __future__ import annotations

from selffork_mind.projections.markdown import (
    MarkdownProjection,
    MarkdownProjectionConfig,
)
from selffork_mind.projections.provenance import (
    ProvenanceEntry,
    ProvenanceRecorder,
)

__all__ = [
    "MarkdownProjection",
    "MarkdownProjectionConfig",
    "ProvenanceEntry",
    "ProvenanceRecorder",
]
