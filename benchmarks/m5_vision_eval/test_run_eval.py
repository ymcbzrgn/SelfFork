"""Offline unit + wiring tests for the M5 R1 vision eval harness.

These run WITHOUT a real vision model (no MLX/Ollama, no GPU). They pin the
harness's *own* correctness — the IoU math, target matching, the R1 pass
rule, report aggregation — and smoke the full scoring pipeline against a
stub adapter over synthetic fixtures. The real R1 gate (``run_eval.py``
``test_r1_gate``, marked ``real_runtime``) still needs a real adapter and is
invoked explicitly by the operator.
"""

from __future__ import annotations

import json

import pytest
import run_eval
import synth
import validate_dataset
from run_eval import (
    _bbox_iou,
    _target_match,
    evaluate_decision,
    score_dataset,
    summarize,
    write_report,
)

from selffork_body.vision import VisionOrchestrator
from selffork_body.vision.runtime import VisionDecision


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _decision(
    action: str = "click",
    target: str = "Sign in",
    bbox: tuple[int, int, int, int] | None = (176, 24, 64, 28),
    *,
    confidence: float = 0.9,
) -> VisionDecision:
    return VisionDecision(
        action=action,
        target=target,
        bbox=bbox,
        args={},
        confidence=confidence,
        reason="stub",
        tier=1,
        duration_ms=1,
    )


class _StubRuntime:
    """Mirrors ``packages/body/tests/vision`` — returns canned JSON payloads.

    Without ``ax_tree_text`` the orchestrator resolves at tier-1 with a single
    ``invoke_with_images`` call, so one payload is popped per task.
    """

    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)

    async def invoke_with_images(
        self, messages, images, max_tokens=256, temperature=0.0, stop=None
    ) -> str:
        return json.dumps(self._payloads.pop(0))


def _payload(task: synth.SyntheticTask, *, correct: bool) -> dict:
    if correct:
        return {
            "action": task.action,
            "target": task.target,
            "bbox": list(task.bbox),
            "args": {},
            "confidence": 0.95,
            "reason": "stub",
        }
    return {
        "action": "wait",
        "target": "nonexistent-element",
        "bbox": [0, 0, 1, 1],
        "args": {},
        "confidence": 0.95,
        "reason": "stub",
    }


# --------------------------------------------------------------------------
# _bbox_iou
# --------------------------------------------------------------------------
def test_bbox_iou_identical() -> None:
    assert _bbox_iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0


def test_bbox_iou_disjoint() -> None:
    assert _bbox_iou([0, 0, 10, 10], [100, 100, 10, 10]) == 0.0


def test_bbox_iou_touching_edges_is_zero() -> None:
    # Shared edge, no area overlap.
    assert _bbox_iou([0, 0, 10, 10], [10, 0, 10, 10]) == 0.0


def test_bbox_iou_half_overlap_known_value() -> None:
    # A area 100, B area 100, intersection 5*10=50, union 150.
    assert _bbox_iou([0, 0, 10, 10], [5, 0, 10, 10]) == pytest.approx(50 / 150)


# --------------------------------------------------------------------------
# _target_match
# --------------------------------------------------------------------------
def test_target_match_lenient_is_bidirectional() -> None:
    assert _target_match("sign in button", "sign in", "lenient")
    assert _target_match("in", "sign in", "lenient")  # predicted ⊆ expected


def test_target_match_strict_is_one_way() -> None:
    assert _target_match("sign in button", "sign in", "strict")
    assert not _target_match("in", "sign in", "strict")


def test_target_match_empty_expected_always_true() -> None:
    assert _target_match("anything", "", "lenient")


# --------------------------------------------------------------------------
# evaluate_decision — the R1 pass rule
# --------------------------------------------------------------------------
def test_evaluate_all_pass() -> None:
    r = evaluate_decision(
        _decision(),
        {"action": "click", "target": "Sign in", "bbox": [176, 24, 64, 28]},
    )
    assert r["pass"] and r["action_ok"] and r["target_ok"] and r["bbox_ok"]
    assert r["bbox_iou"] == pytest.approx(1.0)


def test_evaluate_action_mismatch_fails() -> None:
    r = evaluate_decision(_decision(action="type"), {"action": "click", "target": "Sign in"})
    assert not r["pass"] and not r["action_ok"]


def test_evaluate_target_mismatch_fails() -> None:
    r = evaluate_decision(_decision(target="Cancel"), {"action": "click", "target": "Sign in"})
    assert not r["pass"] and not r["target_ok"]


def test_evaluate_bbox_low_iou_fails() -> None:
    r = evaluate_decision(
        _decision(bbox=(0, 0, 5, 5)),
        {"action": "click", "target": "Sign in", "bbox": [176, 24, 64, 28]},
    )
    assert not r["bbox_ok"] and not r["pass"]


def test_evaluate_missing_expected_bbox_skips_bbox_criterion() -> None:
    r = evaluate_decision(_decision(bbox=None), {"action": "click", "target": "Sign in"})
    assert r["bbox_ok"] and r["bbox_iou"] is None and r["pass"]


def test_evaluate_expected_bbox_but_prediction_none_fails() -> None:
    r = evaluate_decision(
        _decision(bbox=None),
        {"action": "click", "target": "Sign in", "bbox": [1, 2, 3, 4]},
    )
    assert not r["bbox_ok"] and not r["pass"]


# --------------------------------------------------------------------------
# summarize
# --------------------------------------------------------------------------
def test_summarize_accuracy() -> None:
    report = [{"pass": True}, {"pass": True}, {"pass": False}, {"pass": True}]
    assert summarize(report) == {
        "pass_count": 3,
        "total": 4,
        "accuracy": pytest.approx(0.75),
    }


def test_summarize_empty_is_zero() -> None:
    assert summarize([])["accuracy"] == 0.0


# --------------------------------------------------------------------------
# synthetic fixtures
# --------------------------------------------------------------------------
def test_render_png_is_valid_and_clears_validator_floor() -> None:
    png = synth.render_png(256, 192, (176, 24, 64, 28))
    assert png.startswith(b"\x89PNG\r\n\x1a\n")  # PNG magic
    assert b"IHDR" in png and b"IDAT" in png
    assert png[-8:-4] == b"IEND"  # final chunk tag (followed by 4 CRC bytes)
    assert len(png) > validate_dataset.MIN_SCREENSHOT_BYTES


def test_synthetic_corpus_passes_validator(tmp_path, monkeypatch) -> None:
    synth.materialize(tmp_path)
    monkeypatch.setattr(validate_dataset, "DATASET_ROOT", tmp_path)
    monkeypatch.setattr(validate_dataset, "INDEX_FILE", tmp_path / "index.jsonl")
    monkeypatch.setattr(validate_dataset, "TASKS_ROOT", tmp_path / "tasks")
    problems = validate_dataset.collect_drift()
    assert problems == [], problems


# --------------------------------------------------------------------------
# end-to-end scoring pipeline (offline, stub orchestrator)
# --------------------------------------------------------------------------
async def test_score_dataset_end_to_end_all_pass(tmp_path) -> None:
    rows = synth.materialize(tmp_path)
    payloads = [_payload(t, correct=True) for t in synth.SYNTHETIC_TASKS]
    orch = VisionOrchestrator(_StubRuntime(payloads), audit_emit=lambda c, p: None)
    report = await score_dataset(rows, orch.decide, dataset_root=tmp_path)
    s = summarize(report)
    assert s["total"] == len(rows)
    assert s["accuracy"] == pytest.approx(1.0)
    assert all(r["pass"] for r in report)


async def test_score_dataset_detects_failures_below_gate(tmp_path) -> None:
    rows = synth.materialize(tmp_path)
    payloads = [_payload(t, correct=False) for t in synth.SYNTHETIC_TASKS]
    orch = VisionOrchestrator(_StubRuntime(payloads), audit_emit=lambda c, p: None)
    report = await score_dataset(rows, orch.decide, dataset_root=tmp_path)
    s = summarize(report)
    assert s["accuracy"] < run_eval.R1_THRESHOLD
    assert not any(r["pass"] for r in report)


def test_write_report_roundtrips_jsonl(tmp_path) -> None:
    report = [{"task_id": "t1", "pass": True, "surface": "web"}]
    out = write_report(report, kind="stub", out_dir=tmp_path)
    assert out.is_file()
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[0])["task_id"] == "t1"


# --------------------------------------------------------------------------
# the committed corpus never drifts (mirrors the CI validate step)
# --------------------------------------------------------------------------
def test_committed_dataset_in_sync() -> None:
    assert validate_dataset.collect_drift() == []
