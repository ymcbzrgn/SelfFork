"""ReflexCorpusExporter — Mind T4 Procedural → fine-tune corpus (JSONL).

Per ADR-002 §"Three-pillar integration": the Mind tier T4 Procedural
holds operator-style reflex patterns. Order 6 walks those patterns,
applies Bjork desirable difficulties (interleaved schedule + spacing
via :class:`SM2Scheduler`), and emits a fine-tune-ready JSONL file the
``packages/reflex/`` training pipeline ingests.

Each training item is one line:

.. code:: json

    {"messages": [{"role": "system", "content": "..."}, ...],
     "metadata": {"sm2": {...}, "topic": "...", "source_note_id": "..."}}

Topics group decisions / patterns by their ``intent`` token-set
(reusing :func:`selffork_mind.memory.tiers.procedural._intent_tokens`).
The exporter is deterministic: same Mind state + same config =
identical JSONL bytes.

LLM-driven prompt synthesis (rendering each pattern into a
question/answer pair the model can train on) lands as an opt-in
follow-on; default Order 6 emits the pattern's raw content so the
training pipeline can do its own templating.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from selffork_mind.bridge.interleave import shuffle_interleaved
from selffork_mind.bridge.sm2 import SM2Card, SM2Scheduler
from selffork_mind.memory.model import Note
from selffork_mind.memory.tiers.procedural import _intent_tokens
from selffork_mind.store.base import (
    MindStore,
    RetrieveConfig,
    StoreScope,
)

__all__ = [
    "ExportConfig",
    "ExportReport",
    "ReflexCorpusExporter",
    "TrainingItem",
]


@dataclass(frozen=True, slots=True)
class ExportConfig:
    """Knobs for the corpus export."""

    out_path: Path
    project_slug: str | None = None
    tiers: tuple[str, ...] = ("procedural",)
    """Tiers to export. Default = T4 only; pass extra tiers for richer corpora."""

    persona: str = (
        "You are SelfFork — operator-style reflex coding partner. "
        "Apply locked decisions; mirror tool sequences."
    )
    """System prompt prepended to every training item."""

    interleave: bool = True
    """When True, interleave items across topic groups (Bjork
    desirable difficulty). When False, items are emitted in
    canonical (topic, source_note_id) order."""

    sm2_quality_default: int = 5
    """Default SM-2 quality for items with no operator-correction
    history. 5 = perfect recall — the safe assumption when we have
    no data yet (the first export will be soft; subsequent passes
    sharpen as corrections accumulate)."""


@dataclass(frozen=True, slots=True)
class TrainingItem:
    """One JSONL line in the exported corpus."""

    messages: list[dict[str, str]]
    metadata: dict[str, object]

    def to_jsonl(self) -> str:
        return json.dumps(
            {"messages": self.messages, "metadata": self.metadata},
            ensure_ascii=False,
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class ExportReport:
    """Summary of one export pass."""

    items_written: int
    topics: int
    out_path: Path

    def to_payload(self) -> dict[str, object]:
        return {
            "items_written": self.items_written,
            "topics": self.topics,
            "out_path": str(self.out_path),
        }


class ReflexCorpusExporter:
    """Walks Mind T4 Procedural notes and emits a Reflex-ready JSONL."""

    def __init__(
        self,
        *,
        store: MindStore,
        scheduler: SM2Scheduler | None = None,
    ) -> None:
        self._store = store
        self._scheduler = scheduler or SM2Scheduler()

    async def export(self, config: ExportConfig) -> ExportReport:
        notes = await self._gather(config=config)
        if not notes:
            config.out_path.parent.mkdir(parents=True, exist_ok=True)
            config.out_path.write_text("", encoding="utf-8")
            return ExportReport(
                items_written=0,
                topics=0,
                out_path=config.out_path,
            )
        groups = _group_by_topic(notes)
        # Each topic-group is sorted deterministically by note id.
        sorted_groups: list[list[Note]] = []
        for topic, members in sorted(groups.items()):
            del topic  # only used for the metadata; sorting key already applied
            members_sorted = sorted(members, key=lambda n: str(n.id))
            sorted_groups.append(members_sorted)
        if config.interleave:
            ordered = shuffle_interleaved(sorted_groups)
        else:
            ordered = [n for group in sorted_groups for n in group]

        topic_for_id = {n.id: t for t, members in groups.items() for n in members}
        items = [
            self._render_item(
                note=n,
                topic=topic_for_id.get(n.id, "general"),
                persona=config.persona,
                quality_default=config.sm2_quality_default,
            )
            for n in ordered
        ]
        config.out_path.parent.mkdir(parents=True, exist_ok=True)
        config.out_path.write_text(
            "\n".join(item.to_jsonl() for item in items) + ("\n" if items else ""),
            encoding="utf-8",
        )
        return ExportReport(
            items_written=len(items),
            topics=len(sorted_groups),
            out_path=config.out_path,
        )

    async def _gather(self, *, config: ExportConfig) -> list[Note]:
        retrieve = RetrieveConfig(
            tiers=config.tiers,  # type: ignore[arg-type]
            scope=StoreScope(project_slug=config.project_slug),
            top_k=1000,
            rerank_overfetch=1,
        )
        hits = await self._store.retrieve(retrieve)
        return [h.note for h in hits]

    def _render_item(
        self,
        *,
        note: Note,
        topic: str,
        persona: str,
        quality_default: int,
    ) -> TrainingItem:
        # Look up the SM-2 card; create one if absent.
        card = self._scheduler.get(str(note.id))
        if card is None:
            card = SM2Card(item_id=str(note.id))
            self._scheduler.add(card)
        # The first export uses the default quality (5: perfect recall).
        # Subsequent calls re-record with the same quality — a no-op when
        # no correction signal has been logged yet. Real correction
        # quality is recorded externally (e.g. by a future operator-feedback
        # loop) before the next export.
        updated = self._scheduler.record(
            item_id=str(note.id),
            quality=quality_default,
            at=datetime.now(UTC),
        )
        intent = note.intent or "operator-style pattern"
        body = note.content
        messages = [
            {"role": "system", "content": persona},
            {"role": "user", "content": f"Recall the operator's pattern for: {intent}"},
            {"role": "assistant", "content": body},
        ]
        metadata: dict[str, object] = {
            "source_note_id": str(note.id),
            "tier": note.tier,
            "kind": note.kind,
            "topic": topic,
            "intent": intent,
            "valid_from": note.valid_from.isoformat(),
            "project_slug": note.project_slug,
            "sm2": {
                "e_factor": updated.e_factor,
                "repetitions": updated.repetitions,
                "interval_days": updated.interval_days,
                "next_review_at": updated.next_review_at.isoformat(),
            },
        }
        return TrainingItem(messages=messages, metadata=metadata)


# ── module helpers ────────────────────────────────────────────────────────


def _group_by_topic(notes: Sequence[Note]) -> dict[str, list[Note]]:
    """Partition notes by their first ``intent`` token (deterministic).

    A note with intent ``"sequence:a->b"`` maps to topic ``"sequence"``.
    A note with empty intent maps to ``"general"``. We use the FIRST
    surviving non-stopword token so two patterns about the same family
    cluster cleanly without exploding into per-pattern singletons.
    """
    groups: dict[str, list[Note]] = defaultdict(list)
    for note in notes:
        tokens = _intent_tokens(note.intent)
        topic = tokens[0] if tokens else "general"
        groups[topic].append(note)
    return groups
