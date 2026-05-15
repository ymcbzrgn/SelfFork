"""Prompt templates for the Gemma 4 vision pipeline (ADR-005 §M5-B).

Three tiers of escalating context:

* **Tier-1 (default):** locate-by-label JSON output. Single screenshot,
  no DOM/AX hint. Fastest path; >=0.7 confidence required to commit.
* **Tier-2 (fallback):** ROI crop + DOM/AX-tree text + previous tier
  confidence. Used when Tier-1 confidence drops below threshold.
* **Tier-3 (last resort):** Set-of-Marks overlay + numeric click index.
  Q4_0 reliability not yet benchmarked — gate per session.
"""

from __future__ import annotations

import json
from typing import Literal

__all__ = [
    "Tier",
    "build_prompt",
    "parse_decision",
]


Tier = Literal[1, 2, 3]


_TIER1_TEMPLATE = """\
You are a UI control agent. Look at the screenshot and decide the next action.

Goal: {goal}

Available actions:
- click(target_description, bbox?, button?)
- type(text, target?)
- swipe(direction, amount?)
- scroll(direction, amount?)
- press_key(key_combo)
- wait(ms)

Return ONLY a single JSON object on one line:
{{"action": "<action_name>", "target": "<short element description>", "bbox": [x, y, w, h] | null, "args": {{}}, "confidence": <float 0..1>, "reason": "<one sentence>"}}

Do not include any text before or after the JSON.
"""

_TIER2_SUFFIX = """

DOM / accessibility tree summary:
{ax_tree_text}

Previous tier-1 confidence was {prev_confidence}. Re-examine the cropped
region carefully and provide a fresh decision.
"""

_TIER3_SUFFIX = """

A Set-of-Marks overlay has been applied. Click target by index number visible
on the screenshot. Available marks: {marks_summary}
"""


def build_prompt(
    *,
    tier: Tier,
    goal: str,
    ax_tree_text: str | None = None,
    prev_confidence: float | None = None,
    marks_summary: str | None = None,
) -> str:
    """Render a prompt string for the requested tier."""
    if tier == 1:
        return _TIER1_TEMPLATE.format(goal=goal)
    if tier == 2:
        if not ax_tree_text:
            raise ValueError("tier 2 requires ax_tree_text")
        body = _TIER1_TEMPLATE.format(goal=goal)
        return body + _TIER2_SUFFIX.format(
            ax_tree_text=ax_tree_text,
            prev_confidence=f"{prev_confidence:.2f}" if prev_confidence is not None else "n/a",
        )
    if tier == 3:
        if not marks_summary:
            raise ValueError("tier 3 requires marks_summary")
        base = build_prompt(
            tier=2,
            goal=goal,
            ax_tree_text=ax_tree_text or "(none)",
            prev_confidence=prev_confidence,
        )
        return base + _TIER3_SUFFIX.format(marks_summary=marks_summary)
    raise ValueError(f"unknown tier: {tier!r}")


def parse_decision(raw: str) -> dict:
    """Parse the LLM-emitted single-line JSON decision.

    Strips fences and leading/trailing junk that some models still produce.
    Raises :class:`ValueError` on any structural problem.
    """
    text = raw.strip()
    if text.startswith("```"):
        # Strip ``` … ``` fences if present.
        lines = [line for line in text.splitlines() if not line.startswith("```")]
        text = "\n".join(lines).strip()
    try:
        decision = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"vision output is not valid JSON: {exc}; raw={text!r}") from exc
    if not isinstance(decision, dict):
        raise ValueError(f"vision output must be a JSON object, got {type(decision).__name__}")
    required = {"action", "target", "confidence"}
    missing = required - decision.keys()
    if missing:
        raise ValueError(f"vision output missing keys: {sorted(missing)}; raw={text!r}")
    return decision
