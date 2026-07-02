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
    "derive_sm2_quality",
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

    correction_penalty_per_hit: int = 1
    """SM-2 quality points subtracted per linked operator correction
    (ADR-010 Order-6 signal). Zero linked corrections leave quality at
    ``sm2_quality_default`` (100% backward-compatible); every correction
    that shaped a pattern lowers its quality by this many points so a
    frequently-corrected reflex earns a shorter SM-2 review interval.
    Set to 0 to disable the signal and restore the pre-ADR-010
    hardcoded-quality behaviour."""

    correction_quality_floor: int = 2
    """Lower bound the correction penalty cannot push quality below,
    kept inside SM-2's valid [0, 5] band. 2 = "partially used" so a
    heavily-corrected pattern still trains (never a hard 0 "blackout"
    from correction frequency alone). Must satisfy
    ``0 <= correction_quality_floor <= sm2_quality_default``."""


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
        correction_ids = await self._gather_correction_ids(config=config)
        items = [
            self._render_item(
                note=n,
                topic=topic_for_id.get(n.id, "general"),
                persona=config.persona,
                quality_default=config.sm2_quality_default,
                correction_ids=correction_ids,
                quality_floor=config.correction_quality_floor,
                penalty_per_hit=config.correction_penalty_per_hit,
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

    async def _gather_correction_ids(self, *, config: ExportConfig) -> frozenset[str]:
        """IDs of operator-correction notes in the corpus's scope.

        Corrections are T2 Episodic ``decision`` notes stamped with a
        ``source_pointer='correction:<key>'`` by
        :func:`selffork_mind.ingest.heartbeat.correction_entry_to_note`.
        We fetch the episodic tier in the *same* scope the corpus is
        exported from, so any correction that could have fed a distilled
        ``decision_theme`` pattern (the distiller runs in that same scope)
        is visible here for the provenance match in
        :func:`_correction_hit_count`.
        """
        retrieve = RetrieveConfig(
            tiers=("episodic",),
            scope=StoreScope(project_slug=config.project_slug),
            top_k=1000,
            rerank_overfetch=1,
        )
        hits = await self._store.retrieve(retrieve)
        return frozenset(
            str(h.note.id)
            for h in hits
            if (h.note.source_pointer or "").startswith("correction:")
        )

    def _render_item(
        self,
        *,
        note: Note,
        topic: str,
        persona: str,
        quality_default: int,
        correction_ids: frozenset[str],
        quality_floor: int,
        penalty_per_hit: int,
    ) -> TrainingItem:
        # Look up the SM-2 card; create one if absent.
        card = self._scheduler.get(str(note.id))
        if card is None:
            card = SM2Card(item_id=str(note.id))
            self._scheduler.add(card)
        # ADR-010 Order-6: derive the SM-2 quality from how often the
        # operator corrected this pattern. An item with no linked
        # corrections keeps ``quality_default`` (perfect recall), so the
        # first export -- before any corrections accumulate -- stays
        # byte-for-byte identical to the pre-ADR-010 behaviour. As
        # corrections pile onto a pattern, its quality drops (down to
        # ``quality_floor``), shortening its SM-2 review interval so the
        # trainer revisits shaky reflexes sooner.
        correction_hits = _correction_hit_count(note, correction_ids)
        quality = derive_sm2_quality(
            quality_default=quality_default,
            floor=quality_floor,
            penalty_per_hit=penalty_per_hit,
            correction_hits=correction_hits,
        )
        updated = self._scheduler.record(
            item_id=str(note.id),
            quality=quality,
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


def derive_sm2_quality(
    *,
    quality_default: int,
    floor: int,
    penalty_per_hit: int,
    correction_hits: int,
) -> int:
    """Map an item's operator-correction count to an SM-2 quality [0, 5].

    Pure and deterministic (ADR-010 Order-6 signal):

    .. code:: text

        low     = max(0, min(floor, quality_default))
        quality = clamp(quality_default - penalty_per_hit * hits, low, 5)

    ``hits == 0`` returns ``quality_default`` unchanged, so an item with no
    linked corrections reproduces the pre-ADR-010 hardcoded-quality
    behaviour exactly (the backward-compat guarantee). Each linked
    correction shaves ``penalty_per_hit`` points -- harder recall, lower
    quality, shorter SM-2 interval -- clamped so quality never drops below
    ``floor`` nor leaves SM-2's valid [0, 5] band. Negative ``hits`` are
    treated as 0.
    """
    hits = max(0, correction_hits)
    raw = quality_default - penalty_per_hit * hits
    low = max(0, min(floor, quality_default))
    return max(0, min(5, max(low, raw)))


def _correction_hit_count(note: Note, correction_ids: frozenset[str]) -> int:
    """Count operator corrections that provably shaped this pattern.

    Linkage (documented design decision, ADR-010): the data model has NO
    foreign key from an operator correction to the Procedural pattern it
    corrected. The one first-class provenance link that DOES exist is the
    ``decision_ids`` list a ``decision_theme`` pattern records in its JSON
    body (see
    ``ProceduralDistiller._decision_theme_patterns``). Operator
    corrections are themselves T2 Episodic ``decision`` notes
    (``source_pointer='correction:<key>'``), so a correction that fed the
    theme appears among those ids. The hit count is therefore the size of
    ``decision_ids INTERSECT correction_ids``.

    Patterns whose body carries no ``decision_ids`` (``tool_sequence``,
    ``sentinel_routine``) have no per-item correction provenance in the
    current data model, so they return 0 and keep the default quality.
    This is a deliberate, conservative scope choice flagged for review --
    not a silent gap. If a richer correction->pattern link lands later,
    only this function changes.
    """
    if not correction_ids:
        return 0
    try:
        payload = json.loads(note.content)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    raw_ids = payload.get("decision_ids")
    if not isinstance(raw_ids, list):
        return 0
    return sum(
        1 for did in raw_ids if isinstance(did, str) and did in correction_ids
    )


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
