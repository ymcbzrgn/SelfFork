"""LatencyTracker — rolling window + p50/p95/p99 percentile."""

from __future__ import annotations

from selffork_body.vision import LatencyBreakdown, LatencyTracker


def _bd(total_ms: float) -> LatencyBreakdown:
    return LatencyBreakdown(
        image_encode_ms=None,
        prefill_ms=None,
        decode_ms=None,
        total_ms=total_ms,
    )


def test_empty_stats() -> None:
    tracker = LatencyTracker(window=10)
    assert tracker.stats() == {"count": 0}


def test_record_and_stats() -> None:
    tracker = LatencyTracker(window=10)
    for v in (100, 200, 300, 400, 500):
        tracker.record(_bd(float(v)))
    stats = tracker.stats()
    assert stats["count"] == 5
    assert stats["total_p50_ms"] == 300
    assert stats["total_p95_ms"] == 500
    assert stats["total_p99_ms"] == 500
    assert stats["total_mean_ms"] == 300


def test_window_bounded() -> None:
    tracker = LatencyTracker(window=3)
    for v in (1, 2, 3, 4, 5):
        tracker.record(_bd(float(v)))
    assert tracker.count == 3
    stats = tracker.stats()
    # Last 3: 3, 4, 5 → mean 4
    assert stats["total_mean_ms"] == 4


def test_clear_resets() -> None:
    tracker = LatencyTracker()
    tracker.record(_bd(100))
    tracker.clear()
    assert tracker.count == 0
    assert tracker.stats() == {"count": 0}
