"""T4 Procedural — operator-style reflex patterns distilled from Episodic.

Per ADR-002 §1: T4 is "operator-style reflex patterns (tool sequences,
code style, debug routines)". Crucially, T4 is the **fine-tune corpus**
(Pillar 1's training set auto-builds here as the operator works).

The distiller is **deterministic** — no LLM. It walks recent Episodic
notes and extracts patterns the operator's behaviour exhibits:

1. **Tool sequences** — when a tool call X is followed by tool call Y
   in ≥N rounds, that pair becomes a Procedural pattern.
2. **Sentinel routines** — when a sentinel (``[SELFFORK:DONE]``,
   ``[SELFFORK:SPAWN:``) precedes a recurring closing message theme,
   distil it.
3. **Decision themes** — when multiple decisions cluster on the same
   ``intent`` substring, surface the cluster as a single procedural
   pattern with the decision IDs as references.

The distiller is the consolidation pipeline's deterministic-first stage
(ADR-002 §10): cheap pattern-matching, no LLM. LLM-driven distillation
would land in Order 5 alongside the reflection cycle.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from selffork_mind.memory.model import Note
from selffork_mind.memory.tags import Tag
from selffork_mind.store.base import (
    MindStore,
    RetrieveConfig,
    StoreScope,
)

__all__ = [
    "DistillationReport",
    "ProceduralDistiller",
]


@dataclass(frozen=True, slots=True)
class DistillationReport:
    """Summary of one distillation pass.

    Returned to callers (``selffork mind compact``, the orchestrator's
    background memory replay) so they can audit what changed.
    """

    candidates_examined: int
    """Number of Episodic notes that participated in this pass."""

    patterns_written: int
    """New Procedural notes inserted (or upserted)."""

    tool_sequences: int
    """Of ``patterns_written``, how many were tool-sequence patterns."""

    decision_themes: int
    """Of ``patterns_written``, how many were decision-theme patterns."""

    sentinel_routines: int
    """Of ``patterns_written``, how many were sentinel-routine patterns."""

    def to_payload(self) -> dict[str, int]:
        return {
            "candidates_examined": self.candidates_examined,
            "patterns_written": self.patterns_written,
            "tool_sequences": self.tool_sequences,
            "decision_themes": self.decision_themes,
            "sentinel_routines": self.sentinel_routines,
        }


class ProceduralDistiller:
    """Walk Episodic and emit Procedural pattern notes.

    Single-pass, idempotent: rerunning over the same Episodic corpus
    produces the same Procedural notes (UUID5 dedup ensures the second
    pass is a no-op).
    """

    def __init__(
        self,
        *,
        store: MindStore,
        min_pair_count: int = 2,
        min_theme_count: int = 2,
        max_episodic_window: int = 200,
    ) -> None:
        self._store = store
        self._min_pair_count = min_pair_count
        self._min_theme_count = min_theme_count
        self._max_window = max_episodic_window

    async def distil(
        self,
        *,
        project_slug: str | None,
        session_id: str | None = None,
    ) -> DistillationReport:
        """Run one distillation pass over a project's recent Episodic notes."""
        episodic = await self._fetch_episodic(
            project_slug=project_slug,
            session_id=session_id,
        )
        if not episodic:
            return DistillationReport(0, 0, 0, 0, 0)

        tool_pairs = self._extract_tool_pairs(episodic)
        decisions = self._extract_decision_themes(episodic)
        sentinels = self._extract_sentinel_routines(episodic)

        patterns: list[Note] = []
        patterns.extend(self._tool_pair_patterns(tool_pairs, project_slug=project_slug))
        patterns.extend(self._decision_theme_patterns(decisions, project_slug=project_slug))
        patterns.extend(self._sentinel_routine_patterns(sentinels, project_slug=project_slug))

        if patterns:
            await self._store.upsert_notes(patterns)
            tags: list[Tag] = []
            for pattern in patterns:
                tags.append(
                    Tag.now(note_id=pattern.id, key="kind", value="pattern"),
                )
                if project_slug is not None:
                    tags.append(
                        Tag.now(note_id=pattern.id, key="project", value=project_slug),
                    )
                tags.append(
                    Tag.now(note_id=pattern.id, key="distilled_from", value="episodic"),
                )
            await self._store.attach_tags(tags)

        return DistillationReport(
            candidates_examined=len(episodic),
            patterns_written=len(patterns),
            tool_sequences=len(tool_pairs),
            decision_themes=len(decisions),
            sentinel_routines=len(sentinels),
        )

    # ── extractors (pure, deterministic) ──────────────────────────────────

    def _extract_tool_pairs(
        self,
        episodic: Sequence[Note],
    ) -> dict[tuple[str, str], int]:
        """Count ordered ``(tool_a, tool_b)`` pairs across consecutive
        pattern notes (tool calls).
        """
        # Per session, walk pattern notes (tool calls) ordered by valid_from.
        per_session: dict[str | None, list[str]] = defaultdict(list)
        for note in sorted(episodic, key=lambda n: (n.session_id or "", n.valid_from)):
            if note.kind != "pattern":
                continue
            tool = self._extract_tool_name(note)
            if tool is not None:
                per_session[note.session_id].append(tool)

        counts: Counter[tuple[str, str]] = Counter()
        for tools in per_session.values():
            for a, b in pairwise(tools):
                counts[(a, b)] += 1
        return {pair: c for pair, c in counts.items() if c >= self._min_pair_count}

    def _extract_decision_themes(
        self,
        episodic: Sequence[Note],
    ) -> dict[str, list[Note]]:
        """Cluster decisions by **shared** ``intent`` tokens.

        Per-token index: every decision contributes to one group per
        non-stopword token in its intent. Each token whose group has
        ≥``min_theme_count`` decisions becomes its OWN theme (so two
        decisions like "lock embedder bge" + "lock embedder jina"
        produce two separate themes — ``theme:lock`` and
        ``theme:embedder`` — each with the same two member decisions).

        That can look duplicative but is intentional: each token-theme
        becomes a distinct Procedural pattern note (one
        ``intent="theme:lock"`` and one ``intent="theme:embedder"``).
        Downstream HybridRetriever can union them or rank by tag overlap.
        """
        per_token: dict[str, list[Note]] = defaultdict(list)
        for note in episodic:
            if note.kind != "decision":
                continue
            for token in set(_intent_tokens(note.intent)):
                per_token[token].append(note)
        # De-duplicate: when one decision-set is a strict subset of
        # another's, keep only the most-specific (largest) cluster. We
        # want themes that genuinely have ≥N members AND aren't subsumed.
        themes: dict[str, list[Note]] = {}
        for token, members in per_token.items():
            if len(members) < self._min_theme_count:
                continue
            themes[token] = members
        return themes

    def _extract_sentinel_routines(
        self,
        episodic: Sequence[Note],
    ) -> dict[str, list[Note]]:
        """Group observation notes by which sentinel they carry.

        We rely on the Episodic writer's ``sentinel`` tag (see
        ``EpisodicWriter._tags_for_note``). The store's tag query path is
        out of scope here because we already have the notes; instead we
        re-detect sentinels from the rendered content.
        """
        from selffork_mind.memory.tiers.episodic import detect_sentinels

        groups: dict[str, list[Note]] = defaultdict(list)
        for note in episodic:
            if note.kind != "observation":
                continue
            for sentinel in detect_sentinels(note.content):
                groups[sentinel].append(note)
        return {
            sentinel: members
            for sentinel, members in groups.items()
            if len(members) >= self._min_theme_count
        }

    # ── pattern note builders ─────────────────────────────────────────────

    @staticmethod
    def _tool_pair_patterns(
        pairs: dict[tuple[str, str], int],
        *,
        project_slug: str | None,
    ) -> list[Note]:
        return [
            Note(
                tier="procedural",
                kind="pattern",
                content=json.dumps(
                    {
                        "type": "tool_sequence",
                        "first": a,
                        "then": b,
                        "occurrences": count,
                    },
                    ensure_ascii=False,
                ),
                intent=f"sequence:{a}->{b}",
                project_slug=project_slug,
                importance=2.0 + min(count, 8) * 0.25,  # bump up to 4.0
            )
            for (a, b), count in pairs.items()
        ]

    @staticmethod
    def _decision_theme_patterns(
        themes: dict[str, list[Note]],
        *,
        project_slug: str | None,
    ) -> list[Note]:
        out: list[Note] = []
        for theme, members in themes.items():
            sources = [str(n.id) for n in members]
            content = json.dumps(
                {
                    "type": "decision_theme",
                    "theme": theme,
                    "decision_ids": sources,
                    "occurrences": len(sources),
                },
                ensure_ascii=False,
            )
            out.append(
                Note(
                    tier="procedural",
                    kind="pattern",
                    content=content,
                    intent=f"theme:{theme}",
                    project_slug=project_slug,
                    importance=3.0 + min(len(sources), 6) * 0.25,
                ),
            )
        return out

    @staticmethod
    def _sentinel_routine_patterns(
        sentinels: dict[str, list[Note]],
        *,
        project_slug: str | None,
    ) -> list[Note]:
        return [
            Note(
                tier="procedural",
                kind="pattern",
                content=json.dumps(
                    {
                        "type": "sentinel_routine",
                        "sentinel": sentinel,
                        "occurrences": len(members),
                    },
                    ensure_ascii=False,
                ),
                intent=f"sentinel:{sentinel}",
                project_slug=project_slug,
                importance=2.5,
            )
            for sentinel, members in sentinels.items()
        ]

    # ── helpers ───────────────────────────────────────────────────────────

    async def _fetch_episodic(
        self,
        *,
        project_slug: str | None,
        session_id: str | None,
    ) -> list[Note]:
        config = RetrieveConfig(
            tiers=("episodic",),
            scope=StoreScope(project_slug=project_slug, session_id=session_id),
            top_k=self._max_window,
            rerank_overfetch=1,
        )
        hits = await self._store.retrieve(config)
        return [h.note for h in hits]

    @staticmethod
    def _extract_tool_name(note: Note) -> str | None:
        """The Episodic pattern note's content is a JSON tool-call payload
        (see :func:`selffork_mind.memory.tiers.episodic._render_tool_call_content`).
        """
        try:
            payload: dict[str, Any] = json.loads(note.content)
        except (json.JSONDecodeError, ValueError):
            # Fallback: parse from intent ("tool:foo")
            if note.intent.startswith("tool:"):
                return note.intent[len("tool:") :]
            return None
        tool = payload.get("tool")
        if isinstance(tool, str) and tool:
            return tool
        return None


# ── module helpers ────────────────────────────────────────────────────────


_INTENT_TOKEN_STOPWORDS: frozenset[str] = frozenset(
    {"the", "a", "an", "to", "of", "in", "on", "for", "with", "is", "are"},
)


def _intent_tokens(intent: str) -> list[str]:
    """Token set for clustering decision themes — strip stopwords."""
    out: list[str] = []
    for raw in intent.lower().split():
        token = "".join(c for c in raw if c.isalnum())
        if token and token not in _INTENT_TOKEN_STOPWORDS:
            out.append(token)
    return out
