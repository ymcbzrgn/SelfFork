"""Latency profiling for vision calls (ADR-005 §M5-B).

The orchestrator only sees end-to-end ms today; this module exposes a
lightweight ``LatencyBreakdown`` dataclass + helper for backends that can
report per-phase timings (encode / prefill / decode). Cockpit Body tab
surfaces these as p50/p95 gauges in Order 9.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

__all__ = ["LatencyBreakdown", "LatencyTracker"]


@dataclass(frozen=True, slots=True)
class LatencyBreakdown:
    image_encode_ms: float | None
    prefill_ms: float | None
    decode_ms: float | None
    total_ms: float


@dataclass
class LatencyTracker:
    """Rolling-window latency aggregator.

    Window size defaults to 100 — enough for stable p50/p95 without retaining
    unbounded history. Caller pushes ``LatencyBreakdown`` after each vision
    call; the cockpit reads :meth:`stats` periodically.
    """

    window: int = 100
    _samples: list[LatencyBreakdown] = field(default_factory=list)

    def record(self, breakdown: LatencyBreakdown) -> None:
        self._samples.append(breakdown)
        if len(self._samples) > self.window:
            del self._samples[: len(self._samples) - self.window]

    def clear(self) -> None:
        self._samples.clear()

    @property
    def count(self) -> int:
        return len(self._samples)

    def stats(self) -> dict[str, float]:
        if not self._samples:
            return {"count": 0}
        totals = [s.total_ms for s in self._samples]
        sorted_totals = sorted(totals)
        return {
            "count": float(len(totals)),
            "total_p50_ms": _percentile(sorted_totals, 0.5),
            "total_p95_ms": _percentile(sorted_totals, 0.95),
            "total_p99_ms": _percentile(sorted_totals, 0.99),
            "total_mean_ms": statistics.mean(totals),
        }


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if pct <= 0:
        return sorted_values[0]
    if pct >= 1:
        return sorted_values[-1]
    idx = round(pct * (len(sorted_values) - 1))
    return sorted_values[idx]
