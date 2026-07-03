"""Deterministic synthetic fixtures for offline harness smoke tests.

A real R1 task needs a genuine screenshot *and* a genuine vision model
(see ``README.md`` §30-Task Seeding). Neither can be produced in CI or on a
GPU-less machine, so this module renders **synthetic** UI screenshots
(pure-stdlib PNG, no Pillow) with a known target bbox. That is enough to
drive the eval harness end-to-end against a stub adapter and prove its
plumbing — IoU, target matching, aggregation, audit emission.

Synthetic tasks are NEVER the R1 acceptance gate; they only exercise
wiring. ``run_eval.py`` skips any ``sample_*`` id, and this generator is a
test/dev tool — nothing here is committed into the real corpus.

Usage as a tool (materialize a smoke corpus for a manual harness run)::

    uv run python benchmarks/m5_vision_eval/synth.py --out /tmp/synth_corpus
"""

from __future__ import annotations

import argparse
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def render_png(
    width: int,
    height: int,
    bbox: tuple[int, int, int, int],
    *,
    bg: tuple[int, int, int] = (245, 246, 248),
    fg: tuple[int, int, int] = (69, 146, 122),
) -> bytes:
    """Render an 8-bit RGBA PNG: a dithered ``bg`` field + solid ``fg`` box.

    The high-frequency dither keeps the compressed IDAT comfortably above
    ``validate_dataset.MIN_SCREENSHOT_BYTES`` (1 KB), so a synthetic
    screenshot is indistinguishable from a real one to the validator's
    size heuristic. Fully deterministic — no RNG — so fixtures are stable.
    """
    bx, by, bw, bh = bbox
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # PNG scanline filter type 0 (None)
        for x in range(width):
            # A smooth 2D gradient plus a light deterministic dither: pleasant
            # to look at, yet entropic enough that the compressed IDAT clears
            # the validator's 1 KB floor for *any* bbox — including a
            # full-canvas box (which is otherwise a solid, ~500 B field).
            grad = (x * 16) // max(width, 1) + (y * 40) // max(height, 1)
            dither = (x * 73 + y * 151) % 5
            base = fg if (bx <= x < bx + bw and by <= y < by + bh) else bg
            sub = grad + dither
            raw += bytes(max(min(c - sub, 255), 0) for c in base) + b"\xff"
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    return sig + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")


@dataclass(frozen=True)
class SyntheticTask:
    task_id: str
    surface: str
    goal: str
    action: str
    target: str
    bbox: tuple[int, int, int, int]
    canvas: tuple[int, int] = (256, 192)


# A tiny, deterministic corpus: one task per surface + a non-click action,
# so the harness exercises every ``surface`` enum branch and both the
# bbox-present and full-page paths.
SYNTHETIC_TASKS: tuple[SyntheticTask, ...] = (
    SyntheticTask(
        "syn_web_signin",
        "web",
        "click the Sign in button",
        "click",
        "Sign in",
        (176, 24, 64, 28),
    ),
    SyntheticTask(
        "syn_web_search",
        "web",
        "type the query into the search box",
        "type",
        "Search",
        (32, 80, 160, 24),
    ),
    SyntheticTask(
        "syn_macos_settings",
        "macos",
        "click the Settings icon",
        "click",
        "Settings",
        (16, 140, 40, 40),
    ),
    SyntheticTask(
        "syn_android_install",
        "android",
        "tap Install on the Play Store dialog",
        "click",
        "Install",
        (150, 150, 80, 30),
    ),
    SyntheticTask(
        "syn_ios_scroll",
        "ios",
        "scroll down the Safari page",
        "scroll",
        "page",
        (0, 0, 256, 192),
    ),
)


def write_task(root: Path, task: SyntheticTask) -> dict:
    """Materialize one synthetic task under ``root/tasks/<id>/``.

    Returns the ``index.jsonl`` row describing it.
    """
    task_dir = root / "tasks" / task.task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    w, h = task.canvas
    (task_dir / "screenshot.png").write_bytes(render_png(w, h, task.bbox))
    (task_dir / "goal.txt").write_text(task.goal + "\n", encoding="utf-8")
    (task_dir / "expected_action.json").write_text(
        json.dumps(
            {
                "action": task.action,
                "target": task.target,
                "bbox": list(task.bbox),
                "notes": "SYNTHETIC — offline harness smoke only, not an R1 task.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "task_id": task.task_id,
        "surface": task.surface,
        "dir": f"tasks/{task.task_id}",
        "instruction_summary": task.goal,
    }


def materialize(root: Path, tasks: tuple[SyntheticTask, ...] = SYNTHETIC_TASKS) -> list[dict]:
    """Write all ``tasks`` + an ``index.jsonl`` under ``root``; return the rows."""
    rows = [write_task(root, t) for t in tasks]
    (root / "index.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic M5 vision smoke fixtures (offline wiring only)."
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="target directory (index.jsonl + tasks/ are written here)",
    )
    ns = parser.parse_args()
    ns.out.mkdir(parents=True, exist_ok=True)
    rows = materialize(ns.out)
    print(f"Wrote {len(rows)} synthetic tasks to {ns.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
