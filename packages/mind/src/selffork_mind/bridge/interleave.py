"""Deterministic interleaving — Bjork desirable difficulty.

Bjork & Bjork (2011) "Making things hard on yourself, but in a good
way": training items grouped by topic produce inferior long-term
retention compared to interleaved orderings. This helper takes a list
of items partitioned by topic and produces a deterministic interleaved
sequence.

Pure function — same inputs always yield the same output (no random).
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["shuffle_interleaved"]


def shuffle_interleaved[T](
    groups: Sequence[Sequence[T]],
) -> list[T]:
    """Round-robin interleave across topic groups.

    Given ``[[a1, a2, a3], [b1, b2], [c1]]`` returns
    ``[a1, b1, c1, a2, b2, a3]``. When a group runs out we keep
    cycling through the remaining ones in their declaration order;
    no random choice is involved (interleave order = group declaration
    order, which Bjork's desirable-difficulty literature treats as a
    valid practice schedule).
    """
    iters: list[list[T]] = [list(g) for g in groups if g]
    out: list[T] = []
    while iters:
        next_iters: list[list[T]] = []
        for group in iters:
            if not group:
                continue
            out.append(group[0])
            remaining = group[1:]
            if remaining:
                next_iters.append(remaining)
        iters = next_iters
    return out
