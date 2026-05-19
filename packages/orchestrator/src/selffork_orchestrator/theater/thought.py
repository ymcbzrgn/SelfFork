"""Parser for Self Jr's compacted thought — the Live Run Theater bubble.

The Workspace "Live Run" theater shows a thought bubble: a plain-language
line describing what Self Jr is doing. Two sources, in priority order:

1. An explicit ``<thought_summary>...</thought_summary>`` block — the
   target shape of the M7-tuned Speaker prompt template (ADR-006 §5.4.1).
2. Fallback — a best-effort compaction of the round-loop reply with
   protocol syntax (``<selffork-tool-call>`` blocks, ``[SELFFORK:...]``
   sentinels) stripped. The theater is a non-engineer surface, so the
   bubble must never show raw protocol syntax.

The function is deterministic, side-effect-free, and never raises — the
round-loop must not crash on a malformed reply.
"""

from __future__ import annotations

import re

from selffork_orchestrator.theater.models import ThoughtPayload

__all__ = ["parse_thought"]


# Longest summary shown in the bubble; longer text is truncated at a word
# boundary. ADR-006 §5.4.1 keeps the bubble to a few sentences.
_SUMMARY_LIMIT = 280

# Explicit thought block. Mirrors the tag style of
# ``tools.parser._BLOCK_RE``: case-insensitive, DOTALL for a multi-line
# body, non-greedy capture.
_THOUGHT_SUMMARY_RE = re.compile(
    r"<thought_summary>\s*(.*?)\s*</thought_summary>",
    re.IGNORECASE | re.DOTALL,
)

# Protocol syntax stripped from the fallback summary. The tag/sentinel
# shapes mirror ``tools.parser`` and ``spawn.sentinel``.
_TOOL_CALL_RE = re.compile(
    r"<selffork-tool-call>.*?</selffork-tool-call>",
    re.IGNORECASE | re.DOTALL,
)
# Any ``[SELFFORK:...]`` bracket sentinel — DONE, SPAWN, future markers.
_SENTINEL_RE = re.compile(r"\[SELFFORK:[^\]]*\]", re.IGNORECASE)
# Stray thought-summary tags left by a malformed/partial block.
_THOUGHT_TAG_RE = re.compile(r"</?thought_summary>", re.IGNORECASE)

_WHITESPACE_RE = re.compile(r"\s+")


def parse_thought(reply: str) -> ThoughtPayload | None:
    """Extract a compacted thought from a Self Jr round-loop reply.

    Returns ``None`` when the reply carries no human-readable narration
    (e.g. a reply that is purely tool-call blocks) — the caller then
    emits no thought event. ``ThoughtPayload.raw`` always carries the
    unmodified reply for the Settings > Advanced "show raw thinking"
    toggle.
    """
    if not reply or not reply.strip():
        return None

    explicit = _THOUGHT_SUMMARY_RE.search(reply)
    if explicit is not None:
        summary = _collapse_whitespace(explicit.group(1))
        if summary:
            return ThoughtPayload(summary=_truncate(summary), raw=reply)

    cleaned = _collapse_whitespace(_strip_protocol(reply))
    if not cleaned:
        return None
    return ThoughtPayload(summary=_truncate(cleaned), raw=reply)


def _strip_protocol(text: str) -> str:
    """Remove tool-call blocks and ``[SELFFORK:...]`` sentinels."""
    text = _TOOL_CALL_RE.sub(" ", text)
    text = _SENTINEL_RE.sub(" ", text)
    return _THOUGHT_TAG_RE.sub(" ", text)


def _collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _truncate(text: str, *, limit: int = _SUMMARY_LIMIT) -> str:
    """Trim ``text`` to ``limit`` chars, breaking on a word boundary."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space].rstrip()
    return f"{cut}…"
