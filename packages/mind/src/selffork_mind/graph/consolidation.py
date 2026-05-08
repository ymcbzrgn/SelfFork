"""Consolidation pipeline — Episodic / Procedural notes → graph triples.

Per ADR-002 §10 (async two-model consolidation): Order 4 ships the
**deterministic-first** half. Every Episodic / Procedural note becomes:

1. A passage (its content) added to the graph's passage→phrase index.
2. Zero or more triples extracted by deterministic pattern matching:
   - Procedural ``tool_sequence`` JSON → ``(first, "then", then)``.
   - Procedural ``decision_theme`` JSON → ``(theme, "decided", note_id)``
     for each member decision.
   - Tool call observations with predicate-shaped ``intent``
     (``tool:foo``) → ``(operator, "uses", foo)``.
   - Note content matches ``"X uses Y"`` / ``"X is Y"`` simple verbs →
     ``(X, verb, Y)``.

LLM-driven extraction (richer triples, paraphrase-tolerant) lands Order
5 alongside the reflection cycle.

The consolidator is idempotent: re-running over the same corpus
produces the same triples (per-passage triple identity ensures dedup).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from selffork_mind.graph.base import GraphTriple, SemanticGraphStore
from selffork_mind.memory.model import Note
from selffork_mind.store.base import (
    MindStore,
    RetrieveConfig,
    StoreScope,
)

__all__ = [
    "ConsolidationReport",
    "SemanticGraphConsolidator",
    "extract_triples",
]


_PHRASE_RE = re.compile(r"[\w][\w\-]+", flags=re.UNICODE)
_VERB_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Tightened: subject and object are single hyphenated tokens (no
    # interior whitespace). Loose multi-word captures previously
    # produced sloppy triples like ("alpha or oauth", "uses", "bge or
    # beta") that don't align with phrase-node identities and break
    # HippoRAG 2 traversal symmetry.
    (
        "uses",
        re.compile(
            r"\b([\w][\w\-]{0,40})\s+uses\s+([\w][\w\-]{0,40})\b",
            flags=re.IGNORECASE,
        ),
    ),
    (
        "is",
        re.compile(
            r"\b([\w][\w\-]{0,40})\s+is\s+([\w][\w\-]{0,40})\b",
            flags=re.IGNORECASE,
        ),
    ),
    (
        "supersedes",
        re.compile(
            r"\b([\w][\w\-]{0,40})\s+supersedes\s+([\w][\w\-]{0,40})\b",
            flags=re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ConsolidationReport:
    """Summary of a consolidation pass."""

    passages_added: int
    phrases_added: int
    triples_added: int

    def to_payload(self) -> dict[str, int]:
        return {
            "passages_added": self.passages_added,
            "phrases_added": self.phrases_added,
            "triples_added": self.triples_added,
        }


def extract_phrases(text: str, *, max_phrases: int = 50) -> list[str]:
    """Pull short normalised phrases out of free-form text.

    Tokenises on word boundaries, lowercases, dedupes, caps at
    ``max_phrases``. The phrase set is intentionally small — HippoRAG 2's
    PPR walks favour focused seeds.
    """
    seen: set[str] = set()
    out: list[str] = []
    for match in _PHRASE_RE.finditer(text):
        token = match.group(0).lower()
        if len(token) < 3 or token in _STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= max_phrases:
            break
    return out


def extract_triples(note: Note) -> list[GraphTriple]:
    """Deterministic structured-source bypass — no LLM.

    Returns the triples we can confidently derive from one note. Empty
    list when no pattern fires (most notes contribute only as passages).
    """
    triples: list[GraphTriple] = []

    # Procedural patterns (the JSON written by ProceduralDistiller).
    if note.tier == "procedural":
        try:
            payload: dict[str, Any] = json.loads(note.content)
        except (json.JSONDecodeError, ValueError):
            payload = {}
        kind = payload.get("type")
        if kind == "tool_sequence":
            first = str(payload.get("first", "")).strip()
            then = str(payload.get("then", "")).strip()
            if first and then:
                triples.append(
                    GraphTriple(
                        subject=first,
                        predicate="then",
                        obj=then,
                        source_passage_id=note.id,
                        project_slug=note.project_slug,
                    ),
                )
        elif kind == "decision_theme":
            theme = str(payload.get("theme", "")).strip()
            decision_ids = payload.get("decision_ids", [])
            if theme and isinstance(decision_ids, list):
                for raw_id in decision_ids:
                    obj_str = str(raw_id).strip()
                    if not obj_str:
                        continue
                    triples.append(
                        GraphTriple(
                            subject=theme,
                            predicate="decided_in",
                            obj=obj_str,
                            source_passage_id=note.id,
                            project_slug=note.project_slug,
                        ),
                    )

    # Tool-call observations (Episodic patterns from EpisodicWriter).
    if note.tier == "episodic" and note.kind == "pattern":
        try:
            payload = json.loads(note.content)
        except (json.JSONDecodeError, ValueError):
            payload = {}
        tool = payload.get("tool")
        if isinstance(tool, str) and tool:
            triples.append(
                GraphTriple(
                    subject="operator",
                    predicate="uses",
                    obj=tool,
                    source_passage_id=note.id,
                    project_slug=note.project_slug,
                ),
            )

    # Free-form pattern matches over note content.
    triples.extend(_extract_verb_triples(note))
    return triples


def _extract_verb_triples(note: Note) -> list[GraphTriple]:
    out: list[GraphTriple] = []
    seen: set[tuple[str, str, str]] = set()
    for predicate, pattern in _VERB_PATTERNS:
        for match in pattern.finditer(note.content):
            subj = match.group(1).strip().lower()
            obj = match.group(2).strip().lower()
            if not subj or not obj or subj == obj:
                continue
            if (subj, predicate, obj) in seen:
                continue
            seen.add((subj, predicate, obj))
            out.append(
                GraphTriple(
                    subject=subj,
                    predicate=predicate,
                    obj=obj,
                    source_passage_id=note.id,
                    project_slug=note.project_slug,
                    confidence=0.7,
                ),
            )
    return out


class SemanticGraphConsolidator:
    """Walks Mind notes and builds the semantic graph deterministically."""

    def __init__(
        self,
        *,
        store: MindStore,
        graph: SemanticGraphStore,
        max_window: int = 500,
    ) -> None:
        self._store = store
        self._graph = graph
        self._max_window = max_window

    async def consolidate(
        self,
        *,
        project_slug: str | None,
    ) -> ConsolidationReport:
        # Pull every Episodic + Procedural note in scope. Working / Reflection
        # tiers are excluded — T1 is volatile, T5 lands Order 5.
        config = RetrieveConfig(
            tiers=("episodic", "procedural"),
            scope=StoreScope(project_slug=project_slug),
            top_k=self._max_window,
            rerank_overfetch=1,
        )
        hits = await self._store.retrieve(config)
        passages_added = 0
        phrases_added = 0
        all_phrases: set[str] = set()
        all_triples: list[GraphTriple] = []
        for hit in hits:
            phrases = extract_phrases(hit.note.content)
            await self._graph.add_passage(passage_id=hit.note.id, phrases=phrases)
            passages_added += 1
            for phrase in phrases:
                if phrase not in all_phrases:
                    all_phrases.add(phrase)
                    phrases_added += 1
            all_triples.extend(extract_triples(hit.note))
        if all_triples:
            await self._graph.add_triples(all_triples)
        return ConsolidationReport(
            passages_added=passages_added,
            phrases_added=phrases_added,
            triples_added=len(all_triples),
        )


# ── module helpers ────────────────────────────────────────────────────────


_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "as",
        "at",
        "by",
        "from",
        "we",
        "us",
        "our",
        "you",
        "your",
        "they",
        "them",
        "their",
        "do",
        "does",
        "did",
        "not",
        "no",
        "but",
        "if",
        "than",
        "then",
        "so",
        "ok",
        "yes",
        "round",
        "operator",
        "cli",
    },
)
