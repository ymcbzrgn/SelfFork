"""S-Train item T2 -- corpus assembler (multi-session -> one flat corpus).

Runs the T1 normalizer (:mod:`selffork_reflex.data.normalize`) over many
sessions and flattens the per-session :class:`~.normalize.TrainingSample`
records into a single corpus, honoring the source precedence in
``docs/Operator_Locked_Decisions.md`` section 4. Serializes to the corpus
JSONL artifact that S-Train item T4 (``selffork train --dataset auto``) writes
and item T5 (:mod:`selffork_reflex.data.validate`) checks.

Each sample keeps its full session prefix as context and targets one operator
(Yamac) message -- exactly what T1 emits; T2 adds the cross-session flattening,
source tagging, and precedence ordering.

Sources
-------
Only SelfFork's OWN session audit has a reader today (T1 +
``session_events_from_audit``); the external Claude Code / OpenCode / ChatGPT
readers are a later S-Train item (see :mod:`.normalize` module docstring). The
:data:`SOURCE_PRECEDENCE` table below is the full section-4 ordering so those
sources slot in by rank the moment their readers land -- ``self_audit`` is the
sole wired source now. Purity is preserved: this module imports only its
sibling :mod:`.normalize`, so ``selffork-reflex`` stays dependency-free.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from selffork_reflex.data.normalize import (
    SYSTEM_PROMPT,
    SessionEvent,
    TrainingSample,
    normalize_session,
)

__all__ = [
    "SOURCE_PRECEDENCE",
    "CorpusSample",
    "SessionCapture",
    "assemble_corpus",
    "corpus_to_jsonl",
    "sample_to_dict",
    "source_rank",
    "write_corpus",
]

# Source precedence, highest first (Operator_Locked_Decisions.md section 4):
#   Primary   -> Claude Code session JSONL, OpenCode export
#   Secondary -> ChatGPT export, Claude.ai ARGE history
#   Auto tier -> Mind T4 Procedural (ADR-002)
#   self_audit -> SelfFork's own session audit; the ONLY reader wired today (T1).
# When the same operator turn appears in several sources, the lower-ranked
# duplicate should yield to the higher-ranked one; ordering here makes that
# precedence explicit and stable.
SOURCE_PRECEDENCE: tuple[str, ...] = (
    "claude_code",
    "opencode",
    "chatgpt",
    "arge",
    "mind_t4",
    "self_audit",
    # Cold-start tool-mastery corpus authored by the teacher (Claude) and gated
    # by the real tool registry -- lowest precedence so any real usage wins over
    # it when the same turn later appears in a genuine session log.
    "synthetic",
)
_UNKNOWN_RANK = len(SOURCE_PRECEDENCE)


def source_rank(source: str) -> int:
    """Precedence rank of ``source`` (0 = highest). Unknown sources sort last."""
    try:
        return SOURCE_PRECEDENCE.index(source)
    except ValueError:
        return _UNKNOWN_RANK


@dataclass(frozen=True, slots=True)
class SessionCapture:
    """One session's ordered events tagged with the source it came from.

    ``source`` should be one of :data:`SOURCE_PRECEDENCE` (T5 flags unknown
    sources as a missing-attribution error); ``self_audit`` is the value the
    T4 ``--dataset auto`` path uses for SelfFork's own session log.
    """

    session_id: str
    source: str
    events: Sequence[SessionEvent]


@dataclass(frozen=True, slots=True)
class CorpusSample:
    """A :class:`~.normalize.TrainingSample` tagged with its source.

    The source tag is carried through to the serialized corpus so T5 can check
    source attribution and so downstream review can trace a sample home.
    """

    sample: TrainingSample
    source: str


def assemble_corpus(
    captures: Iterable[SessionCapture],
    *,
    system_prompt: str = SYSTEM_PROMPT,
) -> list[CorpusSample]:
    """Normalize every capture and flatten to a source-ordered corpus.

    For each capture, T1 :func:`~.normalize.normalize_session` emits one sample
    per operator turn (full session prefix as context). Samples are flattened
    across captures, then **stably** sorted by source precedence rank -- so
    higher-precedence sources lead while sessions within a source, and samples
    within a session, keep their original order. Captures with zero operator
    turns contribute nothing.
    """
    corpus: list[CorpusSample] = []
    for capture in captures:
        samples = normalize_session(
            capture.events,
            session_id=capture.session_id,
            system_prompt=system_prompt,
        )
        corpus.extend(CorpusSample(sample=s, source=capture.source) for s in samples)
    # Python's sort is stable: keying on precedence rank alone preserves the
    # capture/prefix order inside each source bucket.
    corpus.sort(key=lambda cs: source_rank(cs.source))
    return corpus


def sample_to_dict(cs: CorpusSample) -> dict[str, object]:
    """Serialize one corpus sample to the JSONL row schema (T5's contract)."""
    s = cs.sample
    return {
        "session_id": s.session_id,
        "source": cs.source,
        "target_index": s.target_index,
        "messages": [
            {"role": m.role, "content": m.content, "loss_weight": m.loss_weight} for m in s.messages
        ],
    }


def corpus_to_jsonl(corpus: Sequence[CorpusSample]) -> str:
    """Render a corpus as newline-delimited JSON (one sample per line)."""
    return "".join(json.dumps(sample_to_dict(cs), ensure_ascii=False) + "\n" for cs in corpus)


def write_corpus(corpus: Sequence[CorpusSample], path: str | Path) -> int:
    """Write the corpus JSONL artifact to ``path``; return the sample count.

    Parent directories are created as needed. Returns ``len(corpus)`` so the
    T4 CLI can report the artifact size without re-reading the file.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(corpus_to_jsonl(corpus), encoding="utf-8")
    return len(corpus)
