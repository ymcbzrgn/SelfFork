"""R1 vision eval harness — 30-task held-out, ≥%85 accuracy gate.

Per ADR-005 §M5 R1 gate (line 571 + M5_Body_Plan.md §3.5):

    pass = action exact match
         AND target case-insensitive substring match
         AND bbox IoU ≥ 0.5     (only when expected_action.bbox present)

Accuracy = pass_count / total. R1 gate = accuracy ≥ 0.85.

Usage::

    .venv/bin/pytest benchmarks/m5_vision_eval/run_eval.py -v
    SELFFORK_R1_ADAPTER=ollama .venv/bin/pytest benchmarks/m5_vision_eval/run_eval.py -v

Per-task results dump to ``~/.selffork/audit/m5_r1_eval_<adapter>_<ts>.jsonl``
for forensic review (audit-compatible JSONL).

Dataset layout::

    benchmarks/m5_vision_eval/
    ├── README.md
    ├── index.jsonl              # master index (task_id → dir mapping)
    ├── tasks/
    │   └── <task_id>/
    │       ├── screenshot.png
    │       ├── goal.txt
    │       └── expected_action.json
    └── validate_dataset.py      # CI hook (index ↔ dir sync)

When ``index.jsonl`` is missing or empty, the test is skipped (acceptable
in CI before the operator has seeded the 30-task corpus).
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from selffork_body.vision.runtime import (
    MlxVlmAdapter,
    OllamaVisionAdapter,
    VisionDecision,
    VisionOrchestrator,
)
from selffork_shared.config import load_settings

R1_THRESHOLD = 0.85
BBOX_IOU_THRESHOLD = 0.5
DATASET_ROOT = Path(__file__).parent
INDEX_FILE = DATASET_ROOT / "index.jsonl"


def _load_dataset() -> list[dict]:
    if not INDEX_FILE.is_file():
        return []
    entries: list[dict] = []
    with INDEX_FILE.open("r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entries.append(json.loads(line))
    return entries


def _bbox_iou(a: list[int], b: list[int]) -> float:
    """IoU of two ``[x, y, w, h]`` bboxes (returns 0.0 on no overlap)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix1 = max(ax, bx)
    iy1 = max(ay, by)
    ix2 = min(ax + aw, bx + bw)
    iy2 = min(ay + ah, by + bh)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def evaluate_decision(decision: VisionDecision, expected: dict) -> dict:
    """Apply the R1 pass rule and return per-criterion + overall pass flag."""
    action_ok = decision.action == expected.get("action")

    expected_target = (expected.get("target") or "").lower().strip()
    predicted_target = (decision.target or "").lower().strip()
    target_ok = (
        not expected_target
        or expected_target in predicted_target
        or predicted_target in expected_target
    )

    bbox_iou: float | None = None
    bbox_ok = True
    expected_bbox = expected.get("bbox")
    if expected_bbox is not None:
        if decision.bbox is None:
            bbox_ok = False
        else:
            bbox_iou = _bbox_iou(list(decision.bbox), list(expected_bbox))
            bbox_ok = bbox_iou >= BBOX_IOU_THRESHOLD

    return {
        "action_ok": action_ok,
        "target_ok": target_ok,
        "bbox_ok": bbox_ok,
        "bbox_iou": bbox_iou,
        "pass": action_ok and target_ok and bbox_ok,
    }


def _adapter_kind() -> str:
    return os.environ.get("SELFFORK_R1_ADAPTER", "mlx").lower()


def _build_adapter(kind: str):  # type: ignore[no-untyped-def]
    cfg = load_settings().vision
    if kind == "mlx":
        return MlxVlmAdapter.from_config(cfg), cfg.mlx_model_id
    if kind == "ollama":
        return OllamaVisionAdapter.from_config(cfg), cfg.ollama_model_tag
    raise ValueError(f"unknown adapter kind: {kind!r} (expected mlx|ollama)")


@pytest.mark.asyncio
async def test_r1_gate() -> None:
    """R1 acceptance gate — pass rate ≥ 85% across the dataset."""
    dataset = _load_dataset()
    if not dataset:
        pytest.skip(
            "dataset index missing or empty; see benchmarks/m5_vision_eval/README.md "
            "for the 30-task seeding protocol",
        )

    kind = _adapter_kind()
    adapter, model_id = _build_adapter(kind)
    orchestrator = VisionOrchestrator(
        tier1=adapter,
        audit_emit=lambda c, p: None,
    )

    report: list[dict] = []
    for entry in dataset:
        task_dir = DATASET_ROOT / entry["dir"]
        screenshot = (task_dir / "screenshot.png").read_bytes()
        goal = (task_dir / "goal.txt").read_text().strip()
        expected = json.loads((task_dir / "expected_action.json").read_text())
        decision = await orchestrator.decide(screenshot=screenshot, goal=goal)
        result = evaluate_decision(decision, expected)
        report.append({
            "task_id": entry["task_id"],
            "surface": entry.get("surface", "unknown"),
            "instruction": goal,
            "expected": expected,
            "predicted": {
                "action": decision.action,
                "target": decision.target,
                "bbox": list(decision.bbox) if decision.bbox else None,
                "confidence": decision.confidence,
                "tier": decision.tier,
                "duration_ms": decision.duration_ms,
            },
            **result,
        })

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = Path.home() / ".selffork" / "audit" / f"m5_r1_eval_{kind}_{timestamp}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for row in report:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    pass_count = sum(1 for r in report if r["pass"])
    total = len(report)
    accuracy = pass_count / total if total else 0.0

    print(f"\n[R1] adapter={kind} model={model_id}")
    print(f"[R1] pass={pass_count}/{total} ({accuracy:.2%})")
    print(f"[R1] report={out}")

    assert accuracy >= R1_THRESHOLD, (
        f"R1 gate FAIL: accuracy {accuracy:.2%} < {R1_THRESHOLD:.0%}; "
        f"see {out} for per-task breakdown."
    )
