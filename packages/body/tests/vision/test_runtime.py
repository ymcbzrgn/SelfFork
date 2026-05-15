"""VisionOrchestrator — tiered fallback chain + audit emit."""

from __future__ import annotations

import json

import pytest

from selffork_body.vision import VisionOrchestrator


class _StubRuntime:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[list[dict], int]] = []

    async def invoke_with_images(
        self,
        messages,
        images,
        max_tokens=256,
        temperature=0.0,
        stop=None,
    ) -> str:
        self.calls.append((list(messages), len(images)))
        payload = self.responses.pop(0)
        return json.dumps(payload)


def _decision_payload(*, confidence: float, action: str = "click") -> dict:
    return {
        "action": action,
        "target": "Submit",
        "bbox": [10, 20, 30, 40],
        "args": {},
        "confidence": confidence,
        "reason": "stub",
    }


@pytest.fixture()
def audit_log() -> list[tuple[str, dict]]:
    return []


def _audit_emit(log: list[tuple[str, dict]]):
    def _emit(category: str, payload: dict) -> None:
        log.append((category, payload))

    return _emit


async def test_tier1_high_confidence_short_circuits(audit_log) -> None:
    runtime = _StubRuntime([_decision_payload(confidence=0.9)])
    orchestrator = VisionOrchestrator(
        runtime,
        tier1_threshold=0.7,
        audit_emit=_audit_emit(audit_log),
    )
    decision = await orchestrator.decide(b"png", "click submit")
    assert decision.tier == 1
    assert decision.action == "click"
    assert len(runtime.calls) == 1
    assert audit_log[0][0] == "body.vision.query"


async def test_tier1_falls_through_to_tier2_when_ax_tree_provided(audit_log) -> None:
    runtime = _StubRuntime(
        [
            _decision_payload(confidence=0.4),
            _decision_payload(confidence=0.8),
        ]
    )
    orchestrator = VisionOrchestrator(
        runtime,
        tier1_threshold=0.7,
        tier2_threshold=0.5,
        audit_emit=_audit_emit(audit_log),
    )
    decision = await orchestrator.decide(
        b"png", "click submit", ax_tree_text="<button label='Submit'>"
    )
    assert decision.tier == 2
    assert len(runtime.calls) == 2
    tiers_in_audit = [payload["tier"] for _, payload in audit_log]
    assert tiers_in_audit == [1, 2]


async def test_no_ax_tree_returns_tier1_even_low_confidence() -> None:
    runtime = _StubRuntime([_decision_payload(confidence=0.3)])
    orchestrator = VisionOrchestrator(runtime, tier1_threshold=0.7)
    decision = await orchestrator.decide(b"png", "x")
    assert decision.tier == 1
    assert decision.confidence == pytest.approx(0.3)


async def test_tier2_falls_through_to_tier3_when_marks_provided() -> None:
    runtime = _StubRuntime(
        [
            _decision_payload(confidence=0.3),
            _decision_payload(confidence=0.4),
            _decision_payload(confidence=0.95),
        ]
    )
    orchestrator = VisionOrchestrator(
        runtime,
        tier1_threshold=0.7,
        tier2_threshold=0.5,
    )
    decision = await orchestrator.decide(
        b"png",
        "x",
        ax_tree_text="(tree)",
        marks_summary="0=submit",
    )
    assert decision.tier == 3
    assert len(runtime.calls) == 3


async def test_audit_emit_includes_duration_and_confidence() -> None:
    runtime = _StubRuntime([_decision_payload(confidence=0.9)])
    log: list[tuple[str, dict]] = []
    orchestrator = VisionOrchestrator(runtime, audit_emit=_audit_emit(log))
    await orchestrator.decide(b"png", "x")
    assert "duration_ms" in log[0][1]
    assert log[0][1]["confidence"] == 0.9
