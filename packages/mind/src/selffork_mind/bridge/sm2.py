"""SM-2 spaced-repetition algorithm (Wozniak 1987) — pure Python.

The SM-2 algorithm assigns each item an "E-Factor" (ease) that adapts
to the operator's correction frequency:

- Higher correction → harder item → lower E-Factor → shorter interval.
- Lower correction → easier item → higher E-Factor → longer interval.

We map SelfFork operator behaviour to the SM-2 quality scale [0, 5]:

- Pattern reused without correction → quality 5 (perfect recall).
- Pattern reused with minor tweak → quality 4.
- Pattern reused with significant rewrite → quality 3 (correct response
  recalled with serious difficulty).
- Pattern partially used → quality 2.
- Pattern abandoned mid-use → quality 1.
- Pattern explicitly superseded → quality 0 (complete blackout).

The mapping is the orchestrator's call (see
:class:`~selffork_mind.bridge.exporter.ReflexCorpusExporter`); this
module just exposes the math.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

__all__ = [
    "SM2Card",
    "SM2Scheduler",
    "sm2_e_factor",
    "sm2_next_review",
]


@dataclass(frozen=True, slots=True)
class SM2Card:
    """One spaced-repetition card.

    A SelfFork bridge "card" wraps one Procedural pattern note id (or
    Decision id). The scheduler updates the card's ease, repetition
    count, and next-review date as the operator interacts with the
    underlying pattern.
    """

    item_id: str
    e_factor: float = 2.5
    repetitions: int = 0
    interval_days: int = 0
    last_reviewed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    next_review_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def sm2_e_factor(*, current: float, quality: int) -> float:
    """Update an E-Factor by one quality observation.

    SM-2's published recurrence (Wozniak 1990):

    .. code:: text

        EF' = max(1.3, EF - 0.8 + 0.28 * q - 0.02 * q²)

    The 1.3 floor prevents an item from drifting into a degenerate
    state where every correction shortens it further.
    """
    if quality < 0 or quality > 5:
        raise ValueError(f"quality must be in [0, 5]; got {quality}")
    new = current - 0.8 + 0.28 * quality - 0.02 * quality * quality
    return max(1.3, new)


def sm2_next_review(
    *,
    repetitions: int,
    interval_days: int,
    e_factor: float,
    quality: int,
    last_reviewed_at: datetime,
) -> tuple[int, int, datetime]:
    """Compute the next ``(repetitions, interval_days, next_review_at)``.

    SM-2 recurrence:

    - q < 3 → reset reps to 0, interval to 1 day.
    - q ≥ 3 → reps += 1; interval grows: rep 1 → 1 day; rep 2 → 6 days;
      rep ≥ 3 → previous_interval * E-Factor.
    """
    if quality < 0 or quality > 5:
        raise ValueError(f"quality must be in [0, 5]; got {quality}")
    if quality < 3:
        new_reps = 0
        new_interval = 1
    else:
        new_reps = repetitions + 1
        if new_reps == 1:
            new_interval = 1
        elif new_reps == 2:
            new_interval = 6
        else:
            new_interval = max(1, round(interval_days * e_factor))
    next_review = last_reviewed_at + timedelta(days=new_interval)
    return new_reps, new_interval, next_review


class SM2Scheduler:
    """Mutable scheduler over a fixed pool of :class:`SM2Card`s.

    Designed for a single SelfFork session (Mind compaction cycle).
    Each :meth:`record` call updates one card; :meth:`due_cards` returns
    the cards due for review at the given moment.
    """

    def __init__(self, cards: list[SM2Card] | None = None) -> None:
        self._cards: dict[str, SM2Card] = {c.item_id: c for c in (cards or [])}

    def add(self, card: SM2Card) -> None:
        self._cards[card.item_id] = card

    def get(self, item_id: str) -> SM2Card | None:
        return self._cards.get(item_id)

    def all(self) -> list[SM2Card]:
        return sorted(self._cards.values(), key=lambda c: c.item_id)

    def record(
        self,
        *,
        item_id: str,
        quality: int,
        at: datetime | None = None,
    ) -> SM2Card:
        """Record one review. Returns the updated card."""
        moment = at if at is not None else datetime.now(UTC)
        card = self._cards.get(item_id)
        if card is None:
            card = SM2Card(item_id=item_id, last_reviewed_at=moment)
        new_ef = sm2_e_factor(current=card.e_factor, quality=quality)
        new_reps, new_interval, next_review = sm2_next_review(
            repetitions=card.repetitions,
            interval_days=card.interval_days,
            e_factor=new_ef,
            quality=quality,
            last_reviewed_at=moment,
        )
        updated = replace(
            card,
            e_factor=new_ef,
            repetitions=new_reps,
            interval_days=new_interval,
            last_reviewed_at=moment,
            next_review_at=next_review,
        )
        self._cards[item_id] = updated
        return updated

    def due_cards(self, *, at: datetime | None = None) -> list[SM2Card]:
        """Cards whose ``next_review_at`` is ≤ ``at`` (default now)."""
        moment = at if at is not None else datetime.now(UTC)
        return sorted(
            (c for c in self._cards.values() if c.next_review_at <= moment),
            key=lambda c: (c.next_review_at, c.item_id),
        )
