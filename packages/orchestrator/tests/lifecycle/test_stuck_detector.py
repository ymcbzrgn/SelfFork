"""Tests for the deterministic agentic-loop StuckDetector (ADR-010 §2.2).

The detector is pure + deterministic, so coverage is exhaustive: every
:class:`StuckReason`, the soft-vs-hard boundary, the no-op exempt path, pure
-text rounds, ``reset()``, constructor validation, and the two helpers.
"""

from __future__ import annotations

import pytest

from selffork_orchestrator.lifecycle.stuck_detector import (
    RecoveryAction,
    StepObservation,
    StuckDetector,
    StuckReason,
    StuckVerdict,
    hash_observation,
    normalize_tool_key,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def test_normalize_tool_key_name_only() -> None:
    assert normalize_tool_key("foo") == "foo"


def test_normalize_tool_key_strips_whitespace() -> None:
    assert normalize_tool_key("  foo  ") == "foo"


def test_normalize_tool_key_empty_args_is_name_only() -> None:
    assert normalize_tool_key("foo", {}) == "foo"


def test_normalize_tool_key_args_order_independent() -> None:
    a = normalize_tool_key("foo", {"b": 1, "a": 2})
    b = normalize_tool_key("foo", {"a": 2, "b": 1})
    assert a == b
    assert a.startswith("foo|")


def test_normalize_tool_key_different_args_differ() -> None:
    assert normalize_tool_key("foo", {"a": 1}) != normalize_tool_key("foo", {"a": 2})


def test_hash_observation_deterministic_and_sized() -> None:
    assert hash_observation("x") == hash_observation("x")
    assert hash_observation("x") != hash_observation("y")
    assert len(hash_observation("x")) == 16


# ── verdict shape ────────────────────────────────────────────────────────────


def test_verdict_tripped_property() -> None:
    assert StuckVerdict(stuck=False).tripped is False
    assert StuckVerdict(stuck=False, recovery=RecoveryAction.NUDGE).tripped is True
    assert StuckVerdict(stuck=True, recovery=RecoveryAction.ABORT).tripped is True


# ── constructor validation ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs",
    [
        {"hard_repeat": 1},
        {"soft_repeat": 0},
        {"soft_repeat": 4, "hard_repeat": 3},
        {"no_change": 1},
        {"consecutive_failure": 0},
        {"oscillation_repeats": 1},
        {"max_cycle_len": 1},
        {"window": 2},  # below the widest check span
    ],
)
def test_constructor_rejects_bad_config(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError, match=r".+"):
        StuckDetector(**kwargs)


def test_constructor_accepts_defaults() -> None:
    StuckDetector()  # must not raise


# ── clear cases ──────────────────────────────────────────────────────────────


def test_distinct_tools_changing_obs_never_trips() -> None:
    detector = StuckDetector()
    for i, tool in enumerate(["a", "b", "c", "d", "e", "f"]):
        verdict = detector.record(StepObservation(tool_key=tool, observation_hash=f"o{i}"))
        assert verdict.stuck is False
        assert verdict.recovery is None


def test_text_rounds_with_distinct_obs_clear() -> None:
    detector = StuckDetector()
    verdict = StuckVerdict(stuck=False)
    for i in range(5):
        verdict = detector.record(StepObservation(tool_key=None, observation_hash=f"o{i}"))
    assert verdict.stuck is False
    assert verdict.recovery is None


# ── same-tool repeat (soft -> hard) ──────────────────────────────────────────


def test_same_tool_soft_then_hard() -> None:
    detector = StuckDetector()  # soft@2, hard@3
    v1 = detector.record(StepObservation("foo|x", "o1"))
    assert v1.recovery is None  # first call: clear

    v2 = detector.record(StepObservation("foo|x", "o2"))
    assert v2.stuck is False
    assert v2.recovery is RecoveryAction.NUDGE
    assert v2.reason is StuckReason.SAME_TOOL_REPEAT
    assert v2.corrective_message is not None
    assert v2.detail["count"] == 2

    v3 = detector.record(StepObservation("foo|x", "o3"))
    assert v3.stuck is True
    assert v3.recovery is RecoveryAction.ABORT
    assert v3.reason is StuckReason.SAME_TOOL_REPEAT
    assert "foo" in (v3.corrective_message or "")
    assert v3.detail["count"] == 3
    assert v3.detail["threshold"] == 3


def test_same_tool_priority_over_no_change() -> None:
    detector = StuckDetector()
    detector.record(StepObservation("foo", "same"))
    detector.record(StepObservation("foo", "same"))
    verdict = detector.record(StepObservation("foo", "same"))
    assert verdict.stuck is True
    assert verdict.reason is StuckReason.SAME_TOOL_REPEAT  # wins the priority order


def test_custom_hard_repeat_two() -> None:
    detector = StuckDetector(hard_repeat=2, soft_repeat=1)
    detector.record(StepObservation("a", "o1"))
    verdict = detector.record(StepObservation("a", "o2"))
    assert verdict.stuck is True
    assert verdict.reason is StuckReason.SAME_TOOL_REPEAT


# ── no observable change ─────────────────────────────────────────────────────


def test_no_observable_change_hard_abort() -> None:
    detector = StuckDetector()
    detector.record(StepObservation("a", "x"))
    detector.record(StepObservation("b", "x"))
    verdict = detector.record(StepObservation("c", "x"))
    assert verdict.stuck is True
    assert verdict.reason is StuckReason.NO_OBSERVABLE_CHANGE
    assert verdict.detail["count"] == 3


def test_text_rounds_no_change_aborts() -> None:
    detector = StuckDetector()
    detector.record(StepObservation(None, "same"))
    detector.record(StepObservation(None, "same"))
    verdict = detector.record(StepObservation(None, "same"))
    assert verdict.stuck is True
    assert verdict.reason is StuckReason.NO_OBSERVABLE_CHANGE


# ── consecutive failure ──────────────────────────────────────────────────────


def test_consecutive_failure_hard_abort() -> None:
    detector = StuckDetector()
    detector.record(StepObservation("a", "o1", succeeded=False))
    detector.record(StepObservation("b", "o2", succeeded=False))
    verdict = detector.record(StepObservation("c", "o3", succeeded=False))
    assert verdict.stuck is True
    assert verdict.reason is StuckReason.CONSECUTIVE_FAILURE
    assert verdict.detail["count"] == 3


def test_failure_streak_resets_on_success() -> None:
    detector = StuckDetector()
    detector.record(StepObservation("a", "o1", succeeded=False))
    detector.record(StepObservation("b", "o2", succeeded=True))
    verdict = detector.record(StepObservation("c", "o3", succeeded=False))
    assert verdict.stuck is False


# ── oscillation (SelfFork-original k-cycle) ──────────────────────────────────


def test_oscillation_two_cycle_hard_abort() -> None:
    detector = StuckDetector()
    verdict = StuckVerdict(stuck=False)
    for i, tool in enumerate(["a", "b", "a", "b", "a", "b"]):
        verdict = detector.record(StepObservation(tool_key=tool, observation_hash=f"o{i}"))
    assert verdict.stuck is True
    assert verdict.reason is StuckReason.OSCILLATION
    assert verdict.detail["cycle_len"] == 2
    assert verdict.detail["repeats"] == 3


def test_two_cycle_below_repeat_threshold_does_not_trip() -> None:
    # a,b,a,b = a 2-cycle repeated only twice; default needs 3 repeats.
    detector = StuckDetector()
    verdict = StuckVerdict(stuck=False)
    for i, tool in enumerate(["a", "b", "a", "b"]):
        verdict = detector.record(StepObservation(tool_key=tool, observation_hash=f"o{i}"))
    assert verdict.stuck is False


def test_oscillation_intermediate_steps_do_not_prematurely_abort() -> None:
    detector = StuckDetector()
    for i, tool in enumerate(["a", "b", "a", "b", "a"]):  # 5 steps, span needs 6
        verdict = detector.record(StepObservation(tool_key=tool, observation_hash=f"o{i}"))
        assert verdict.stuck is False


# ── exempt no-op tools ───────────────────────────────────────────────────────


def test_exempt_tool_never_trips_even_with_same_obs() -> None:
    detector = StuckDetector()
    for _ in range(6):
        verdict = detector.record(StepObservation("wait", "same"))
        assert verdict.stuck is False
        assert verdict.recovery is None


def test_exempt_tool_does_not_block_later_same_tool_run() -> None:
    detector = StuckDetector()
    detector.record(StepObservation("a", "o1"))
    detector.record(StepObservation("wait", "o2"))  # exempt; recorded but clear
    detector.record(StepObservation("a", "o3"))
    detector.record(StepObservation("a", "o4"))
    verdict = detector.record(StepObservation("a", "o5"))  # trailing a,a,a
    assert verdict.stuck is True
    assert verdict.reason is StuckReason.SAME_TOOL_REPEAT


def test_exempt_tool_not_counted_in_oscillation() -> None:
    # alternating a/wait must NOT be flagged as an a-wait oscillation cycle.
    detector = StuckDetector()
    verdict = StuckVerdict(stuck=False)
    for i, tool in enumerate(["a", "wait", "a", "wait", "a", "wait", "a"]):
        verdict = detector.record(StepObservation(tool_key=tool, observation_hash=f"o{i}"))
    assert verdict.stuck is False


# ── reset ────────────────────────────────────────────────────────────────────


def test_reset_clears_history() -> None:
    detector = StuckDetector()
    detector.record(StepObservation("a", "o"))
    detector.record(StepObservation("a", "o"))
    detector.reset()
    verdict = detector.record(StepObservation("a", "o"))  # fresh count of 1
    assert verdict.stuck is False
    assert verdict.recovery is None
