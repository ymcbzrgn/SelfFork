"""CI hook — verify ``index.jsonl`` ↔ ``tasks/<id>/`` directory sync.

Catches the four common drift modes::

    1. index.jsonl row points to a missing directory.
    2. tasks/<id>/ directory exists but is not referenced from index.jsonl.
    3. expected_action.json missing one of the required keys (action/target).
    4. screenshot.png unreadable / zero-byte.

Invoked as a script (CI) **and** as a pytest test (local development)::

    .venv/bin/python benchmarks/m5_vision_eval/validate_dataset.py
    .venv/bin/pytest benchmarks/m5_vision_eval/validate_dataset.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DATASET_ROOT = Path(__file__).parent
INDEX_FILE = DATASET_ROOT / "index.jsonl"
TASKS_ROOT = DATASET_ROOT / "tasks"

REQUIRED_EXPECTED_KEYS = {"action", "target"}
# Action enum mirrors ``prompt.py:34-39``. Keep in sync when the vision
# prompt template changes.
ACTION_ENUM = {"click", "type", "swipe", "scroll", "press_key", "wait"}
SURFACE_ENUM = {"web", "desktop", "android", "ios", "macos"}
# Reject zero-byte / 1x1 placeholder PNGs in real corpus. 1 KB floor is
# permissive (~32x32 PNG fits); the sample placeholder is exempted by
# task_id prefix.
MIN_SCREENSHOT_BYTES = 1024
PLACEHOLDER_PREFIX = "sample_"


def _read_index() -> list[dict]:
    if not INDEX_FILE.is_file():
        return []
    rows: list[dict] = []
    with INDEX_FILE.open("r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rows.append(json.loads(line))
    return rows


def _validate_expected_payload(tid: str, payload: dict) -> list[str]:
    """Deep checks on expected_action.json contents."""
    problems: list[str] = []
    missing = REQUIRED_EXPECTED_KEYS - set(payload)
    if missing:
        problems.append(f"[{tid}] expected_action.json missing keys: {sorted(missing)}")
        return problems

    action = payload.get("action")
    if action not in ACTION_ENUM:
        problems.append(
            f"[{tid}] action {action!r} not in {sorted(ACTION_ENUM)}",
        )

    target = payload.get("target")
    if not isinstance(target, str) or not target.strip():
        problems.append(f"[{tid}] target must be non-empty string, got {target!r}")

    bbox = payload.get("bbox")
    if bbox is not None and (
        not isinstance(bbox, list)
        or len(bbox) != 4
        or not all(isinstance(v, int) and v >= 0 for v in bbox)
    ):
        problems.append(
            f"[{tid}] bbox must be [x, y, w, h] of 4 non-negative ints, got {bbox!r}",
        )

    return problems


def collect_drift() -> list[str]:
    problems: list[str] = []
    index = _read_index()
    referenced: set[str] = set()
    seen_ids: set[str] = set()
    dataset_root_resolved = DATASET_ROOT.resolve()

    for entry in index:
        tid = entry.get("task_id", "<missing>")
        if tid in seen_ids:
            problems.append(f"[{tid}] duplicate task_id in index.jsonl")
        else:
            seen_ids.add(tid)

        surface = entry.get("surface")
        if surface is not None and surface not in SURFACE_ENUM:
            problems.append(
                f"[{tid}] surface {surface!r} not in {sorted(SURFACE_ENUM)}",
            )

        rel = entry.get("dir")
        if not rel:
            problems.append(f"[{tid}] index row missing 'dir'")
            continue
        task_dir = DATASET_ROOT / rel
        task_dir_resolved = task_dir.resolve()
        # Path-traversal guard — ensure dir stays inside dataset root.
        try:
            task_dir_resolved.relative_to(dataset_root_resolved)
        except ValueError:
            problems.append(f"[{tid}] dir {rel!r} escapes dataset root")
            continue
        referenced.add(task_dir_resolved.as_posix())
        if not task_dir.is_dir():
            problems.append(f"[{tid}] dir not found: {rel}")
            continue

        screenshot = task_dir / "screenshot.png"
        if not screenshot.is_file() or screenshot.stat().st_size == 0:
            problems.append(f"[{tid}] screenshot.png missing or empty")
        elif not tid.startswith(PLACEHOLDER_PREFIX) and (
            screenshot.stat().st_size < MIN_SCREENSHOT_BYTES
        ):
            problems.append(
                f"[{tid}] screenshot.png suspiciously small "
                f"({screenshot.stat().st_size} B < {MIN_SCREENSHOT_BYTES} B floor); "
                "use sample_ prefix to opt out for placeholders",
            )

        goal = task_dir / "goal.txt"
        if not goal.is_file() or not goal.read_text().strip():
            problems.append(f"[{tid}] goal.txt missing or empty")

        expected = task_dir / "expected_action.json"
        if not expected.is_file():
            problems.append(f"[{tid}] expected_action.json missing")
        else:
            try:
                payload = json.loads(expected.read_text())
            except json.JSONDecodeError as e:
                problems.append(f"[{tid}] expected_action.json invalid JSON: {e}")
                continue
            problems.extend(_validate_expected_payload(tid, payload))

    if TASKS_ROOT.is_dir():
        for task_dir in sorted(TASKS_ROOT.iterdir()):
            if not task_dir.is_dir():
                continue
            if task_dir.resolve().as_posix() not in referenced:
                problems.append(
                    f"[{task_dir.name}] dir exists but not in index.jsonl",
                )

    return problems


def test_dataset_in_sync() -> None:
    """Run as pytest — fail with a human-readable list of drift items."""
    problems = collect_drift()
    assert not problems, "\n  - " + "\n  - ".join(problems)


def main() -> int:
    problems = collect_drift()
    if problems:
        print("Dataset drift:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"Dataset OK ({len(_read_index())} tasks indexed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
