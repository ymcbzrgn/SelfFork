"""S-Auto Faz E — AIRDetector tests (panic detect + sustained failure)."""

from __future__ import annotations

import pytest

from selffork_orchestrator.heartbeat.actions import LegalAction
from selffork_orchestrator.heartbeat.air import (
    DEFAULT_CONSECUTIVE_FAILURE_THRESHOLD,
    DEFAULT_PANIC_KEYWORDS,
    AIRAlert,
    AIRDetector,
)
from selffork_orchestrator.heartbeat.deliberation import ActionDecision
from selffork_orchestrator.heartbeat.executor import ActionResult


def _decision(reasoning: str) -> ActionDecision:
    return ActionDecision(action=LegalAction.WAIT, reasoning=reasoning)


def _result(outcome: str) -> ActionResult:
    return ActionResult(
        action=LegalAction.WAIT,
        outcome=outcome,  # type: ignore[arg-type]
        summary="test",
    )


# ── Healthy stream — no alert ────────────────────────────────────


def test_healthy_decision_and_result_no_alert() -> None:
    detector = AIRDetector()
    alert = detector.check(
        decision=_decision("normal reasoning"),
        result=_result("executed"),
    )
    assert alert is None


def test_no_decision_no_result_no_alert() -> None:
    detector = AIRDetector()
    alert = detector.check(decision=None, result=None)
    assert alert is None


def test_deferred_outcome_no_alert() -> None:
    detector = AIRDetector()
    alert = detector.check(decision=_decision("ok"), result=_result("deferred"))
    assert alert is None


# ── Panic keyword detection ──────────────────────────────────────


@pytest.mark.parametrize("keyword", list(DEFAULT_PANIC_KEYWORDS[:6]))
def test_panic_keyword_in_reasoning_raises_high_severity(keyword: str) -> None:
    detector = AIRDetector()
    alert = detector.check(
        decision=_decision(f"I think I'm {keyword} right now"),
        result=_result("executed"),
    )
    assert alert is not None
    assert alert.severity == "high"
    assert keyword.lower() in [k.lower() for k in alert.matched_keywords]


def test_panic_keyword_case_insensitive() -> None:
    detector = AIRDetector()
    alert = detector.check(
        decision=_decision("I'M PANICKING right now"),
        result=_result("executed"),
    )
    assert alert is not None
    assert alert.severity == "high"


def test_no_panic_keyword_no_alert() -> None:
    detector = AIRDetector()
    alert = detector.check(
        decision=_decision("Everything is calm and proceeding well"),
        result=_result("executed"),
    )
    assert alert is None


@pytest.mark.parametrize(
    "negated_reasoning",
    [
        "I am not panicking, just being deliberate.",
        "I'm not panicking right now.",
        "I am NOT panicking — everything is fine.",
        "I won't be covering up anything.",
        "Don't violate the freeze; I won't.",
        "I never lied to the operator.",
        "I wasn't panicking earlier and I'm calm now.",
    ],
)
def test_negation_clauses_do_not_trigger_panic(negated_reasoning: str) -> None:
    """Audit fix #2: 'not panicking' must not trigger the alert."""
    detector = AIRDetector()
    alert = detector.check(
        decision=_decision(negated_reasoning),
        result=_result("executed"),
    )
    assert alert is None, f"false positive on {negated_reasoning!r}"


def test_mixed_negation_then_real_panic_still_triggers() -> None:
    """Honest narration of a current panic state still raises an alert."""
    detector = AIRDetector()
    alert = detector.check(
        decision=_decision("I'm not sure why I tried it, but I am panicking now."),
        result=_result("executed"),
    )
    assert alert is not None
    assert alert.severity == "high"


def test_recommended_recovery_is_populated() -> None:
    detector = AIRDetector()
    alert = detector.check(
        decision=_decision("I'm panicking"),
        result=_result("executed"),
    )
    assert alert is not None
    assert alert.recommended_recovery != ""


# ── Sustained failures ───────────────────────────────────────────


def test_failure_threshold_raises_medium_alert() -> None:
    detector = AIRDetector(consecutive_failure_threshold=2)
    # First failure — no alert (below threshold).
    assert detector.check(decision=_decision("ok"), result=_result("failed")) is None
    # Second failure — threshold met.
    alert = detector.check(decision=_decision("ok"), result=_result("failed"))
    assert alert is not None
    assert alert.severity == "medium"
    assert alert.consecutive_failures == 2


def test_executed_resets_failure_streak() -> None:
    detector = AIRDetector(consecutive_failure_threshold=2)
    detector.check(decision=_decision("ok"), result=_result("failed"))
    detector.check(decision=_decision("ok"), result=_result("executed"))
    assert detector.consecutive_failures == 0
    alert = detector.check(decision=_decision("ok"), result=_result("failed"))
    assert alert is None


def test_skipped_outcome_does_not_advance_streak() -> None:
    detector = AIRDetector(consecutive_failure_threshold=2)
    detector.check(decision=_decision("ok"), result=_result("failed"))
    # Skipped — no signal — neither resets nor advances.
    detector.check(decision=_decision("ok"), result=_result("skipped"))
    assert detector.consecutive_failures == 1


# ── Critical severity (panic + failure) ──────────────────────────


def test_panic_plus_failure_streak_critical() -> None:
    detector = AIRDetector(consecutive_failure_threshold=2)
    detector.check(decision=_decision("ok"), result=_result("failed"))
    detector.check(decision=_decision("ok"), result=_result("failed"))
    # Streak hit + panic in same tick — but the streak alert already
    # fired. Reset, then combine in one tick.
    detector.reset()
    detector.check(decision=_decision("ok"), result=_result("failed"))
    alert = detector.check(
        decision=_decision("I'm panicking and failing"),
        result=_result("failed"),
    )
    assert alert is not None
    assert alert.severity == "critical"
    assert alert.consecutive_failures == 2
    assert len(alert.matched_keywords) >= 1


# ── reset ────────────────────────────────────────────────────────


def test_reset_clears_streak() -> None:
    detector = AIRDetector(consecutive_failure_threshold=2)
    detector.check(decision=_decision("ok"), result=_result("failed"))
    assert detector.consecutive_failures == 1
    detector.reset()
    assert detector.consecutive_failures == 0


# ── Defaults ─────────────────────────────────────────────────────


def test_default_panic_keyword_list_nonempty() -> None:
    assert len(DEFAULT_PANIC_KEYWORDS) > 0


def test_default_threshold_is_three() -> None:
    assert DEFAULT_CONSECUTIVE_FAILURE_THRESHOLD == 3


def test_air_alert_is_frozen() -> None:
    alert = AIRAlert(severity="medium", reason="test")
    with pytest.raises(AttributeError):
        alert.reason = "edited"  # type: ignore[misc]
