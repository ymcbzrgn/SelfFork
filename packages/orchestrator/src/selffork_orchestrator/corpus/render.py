"""Canonical rendering of SelfFork tool-call targets (error-surface control).

A tiny model learns the EXACT surface form it is shown, so every training
target renders its ``<selffork-tool-call>`` block ONE canonical way: a fixed
tag, one-line JSON, ``tool`` before ``args``, args left in the caller-provided
(schema) order. Uniform form == minimal variance for the model to learn ==
lower error surface. Every render is proven to round-trip through the real
``parse_tool_calls`` (see the builder + tests).
"""

from __future__ import annotations

import json
from collections.abc import Mapping

__all__ = ["render_target", "render_tool_call"]


def render_tool_call(tool: str, args: Mapping[str, object]) -> str:
    """Render one canonical ``<selffork-tool-call>`` block.

    ``tool`` first, ``args`` second, single-line JSON with standard
    ``", "``/``": "`` separators; ``ensure_ascii=False`` keeps Turkish labels
    readable. Arg order is preserved from ``args`` (the builder passes them in
    schema order).
    """
    body = json.dumps({"tool": tool, "args": dict(args)}, ensure_ascii=False)
    return f"<selffork-tool-call>\n{body}\n</selffork-tool-call>"


def render_target(
    tool: str, args: Mapping[str, object], *, reasoning: str | None = None
) -> str:
    """Render a training target: optional one/two-line reasoning + the block.

    ``reasoning=None`` => a **lean** target (the bare canonical block), used for
    simple, unambiguous calls. A short ``reasoning`` string => a
    reply-with-reasoning target, used for judgement cases (disambiguation,
    plan-vs-act, error recovery) where teaching the *why* lowers error surface.
    """
    block = render_tool_call(tool, args)
    if reasoning:
        return f"{reasoning.strip()}\n{block}"
    return block
