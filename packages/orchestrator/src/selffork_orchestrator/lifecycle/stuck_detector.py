"""Deterministic hard stuck-detector for the agentic round-loop (ADR-010 §2.2).

The 24/7 agentic loop (ADR-010 §2, [[selffork-247-agentic-loop-2026-05-25]]) runs
``observe -> think -> act`` with many tool calls per session. A 2B reflex model
is loop-prone, so this module is the deterministic, LLM-free guard that stops the
loop spinning. It watches the sequence of round steps (one tool call + its
observable result) and fires when the loop is genuinely stuck.

Corpus grounding (MANDATE 9, 2026-05-26 — 16 agentic rivals read):

* skyvern ``detect_tool_loop`` (AGPL, idea-only reimplemented clean):
  same-tool-3x HARD-BLOCK with a *structured corrective* ("use a DIFFERENT
  tool"); reset on tool change. Our threshold mirrors its
  ``MAX_CONSECUTIVE_SAME_TOOL = 3``.
* browser-use ``PageFingerprint`` / ``ActionLoopDetector`` (MIT): no-observable
  -change via a state hash + a consecutive-stagnant counter; normalize-before
  -hash so a genuine repeat collapses. We adopt the recipe but REJECT its
  soft-only 5/8/12 posture (too permissive for a 2B model).
* PraisonAI ``DoomLoopDetector`` (MIT): SHA-256 fingerprints + several orthogonal
  deterministic checks (identical / consecutive-failure / no-progress) + a
  graduated recovery ladder; zero LLM, stdlib only.
* deer-flow ``LoopDetectionMiddleware`` (MIT): two-layer hash repetition + a
  warn -> hard escalation that strips the offending call to force a final answer.

SelfFork-original (the gap no rival fills — skyvern explicitly catches only
A-A-A, never A-B-A-B): a single combined gate that also detects **oscillation**
(a repeating k-cycle), tuned **hard@3** for a 2B model, with a **soft@2** early
nudge, and always returns a structured *corrective* rather than a bare kill so
the loop can self-recover before the hard abort.

The detector is pure + deterministic: feed it a :class:`StepObservation` per
round, get a :class:`StuckVerdict`. No I/O, no audit emit, no model — the
round-loop (``lifecycle/session.py``) owns the wiring + audit + caps. Thresholds
are constructor args so the Settings layer can tune them later
([[no-mvp-full-quality-first-time]] — pluggable from day 1).
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

__all__ = [
    "DEFAULT_CONSECUTIVE_FAILURE",
    "DEFAULT_EXEMPT_TOOLS",
    "DEFAULT_HARD_REPEAT",
    "DEFAULT_MAX_CYCLE_LEN",
    "DEFAULT_NO_CHANGE",
    "DEFAULT_OSCILLATION_REPEATS",
    "DEFAULT_SOFT_REPEAT",
    "DEFAULT_WINDOW",
    "RecoveryAction",
    "StepObservation",
    "StuckDetector",
    "StuckReason",
    "StuckVerdict",
    "hash_observation",
    "normalize_tool_key",
]

# 2B-tuned defaults (ADR-010 §2.2). hard@3 mirrors skyvern's
# MAX_CONSECUTIVE_SAME_TOOL; soft@2 mirrors skyvern enforcement.py warn@2.
DEFAULT_HARD_REPEAT: Final[int] = 3
DEFAULT_SOFT_REPEAT: Final[int] = 2
DEFAULT_NO_CHANGE: Final[int] = 3
DEFAULT_CONSECUTIVE_FAILURE: Final[int] = 3
DEFAULT_OSCILLATION_REPEATS: Final[int] = 3
DEFAULT_MAX_CYCLE_LEN: Final[int] = 4
DEFAULT_WINDOW: Final[int] = 30

# Tools that legitimately repeat / are no-ops never trip the detector
# (browser-use exempts {wait, done, go_back}). Matched by base tool name.
DEFAULT_EXEMPT_TOOLS: Final[frozenset[str]] = frozenset(
    {"wait", "done", "noop", "mark_done", "cancel_pending"},
)


class StuckReason(StrEnum):
    """Why the loop is considered stuck."""

    SAME_TOOL_REPEAT = "same_tool_repeat"
    NO_OBSERVABLE_CHANGE = "no_observable_change"
    CONSECUTIVE_FAILURE = "consecutive_failure"
    OSCILLATION = "oscillation"


class RecoveryAction(StrEnum):
    """What the loop should do on a tripped verdict.

    ``NUDGE`` is the soft layer: inject the corrective into the next prompt and
    keep looping (the model gets one chance to self-correct). ``ABORT`` is the
    hard layer: break the loop — the caller fails the round / asks the operator
    (a 2B loop must NOT keep spending on a wedged model).
    """

    NUDGE = "nudge"
    ABORT = "abort"


@dataclass(frozen=True, slots=True)
class StepObservation:
    """One round of the agentic loop, reduced to what the detector needs.

    Attributes:
        tool_key: normalized identity of the action taken this round (tool name
            + salient args — see :func:`normalize_tool_key`). ``None`` when the
            round took no tool action (pure text); a ``None`` key never trips the
            same-tool / oscillation checks but still counts toward no-change.
        observation_hash: hash of the observable result/state AFTER the round
            (see :func:`hash_observation`). Equal hashes across rounds mean
            nothing changed.
        succeeded: whether the round's tool action succeeded; ``False`` feeds the
            consecutive-failure check.
    """

    tool_key: str | None
    observation_hash: str
    succeeded: bool = True


@dataclass(frozen=True, slots=True)
class StuckVerdict:
    """The detector's decision after recording one step.

    Three shapes:

    * ``stuck=False, recovery=None`` — clear, keep looping.
    * ``stuck=False, recovery=NUDGE`` — soft early-warning; keep looping but
      inject ``corrective_message`` into the next prompt.
    * ``stuck=True, recovery=ABORT`` — hard stop; the loop breaks and the caller
      surfaces ``corrective_message`` as the fail reason / operator check-in.
    """

    stuck: bool
    reason: StuckReason | None = None
    recovery: RecoveryAction | None = None
    corrective_message: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def tripped(self) -> bool:
        """``True`` for any non-clear verdict (soft NUDGE or hard ABORT)."""
        return self.recovery is not None


def normalize_tool_key(tool: str, args: dict[str, Any] | None = None) -> str:
    """Build a stable identity for a tool call so genuine repeats collapse.

    Normalizes ``args`` to canonical JSON (sorted keys) before joining, so two
    calls with identical semantics but different dict ordering hash the same
    (browser-use ``_normalize_action_for_hash`` pattern). Returns ``tool`` alone
    when there are no args. The base name is everything before the first ``|``,
    which the detector uses for the exempt-tool check.
    """
    name = tool.strip()
    if not args:
        return name
    canonical = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    return f"{name}|{canonical}"


def hash_observation(text: str) -> str:
    """Return the SHA-256 (first 16 hex chars) of the observable result text.

    Used to detect "no observable change" — equal hashes across consecutive
    rounds mean the loop produced nothing new. SHA-256, not md5 (ruff S324).
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _base_name(tool_key: str | None) -> str | None:
    """The bare tool name (everything before the first ``|``), or ``None``."""
    if tool_key is None:
        return None
    return tool_key.split("|", 1)[0]


class StuckDetector:
    """Deterministic, stateful, single-session agentic-loop stuck-detector.

    Construct once per agentic session; call :meth:`record` after every round
    with a :class:`StepObservation` and act on the returned :class:`StuckVerdict`.
    Not thread-safe by design — one detector per single-threaded loop.
    """

    def __init__(
        self,
        *,
        hard_repeat: int = DEFAULT_HARD_REPEAT,
        soft_repeat: int = DEFAULT_SOFT_REPEAT,
        no_change: int = DEFAULT_NO_CHANGE,
        consecutive_failure: int = DEFAULT_CONSECUTIVE_FAILURE,
        oscillation_repeats: int = DEFAULT_OSCILLATION_REPEATS,
        max_cycle_len: int = DEFAULT_MAX_CYCLE_LEN,
        window: int = DEFAULT_WINDOW,
        exempt_tools: frozenset[str] = DEFAULT_EXEMPT_TOOLS,
    ) -> None:
        if hard_repeat < 2:
            raise ValueError("hard_repeat must be >= 2")
        if not 1 <= soft_repeat <= hard_repeat:
            raise ValueError("soft_repeat must satisfy 1 <= soft_repeat <= hard_repeat")
        if no_change < 2:
            raise ValueError("no_change must be >= 2")
        if consecutive_failure < 1:
            raise ValueError("consecutive_failure must be >= 1")
        if oscillation_repeats < 2:
            raise ValueError("oscillation_repeats must be >= 2")
        if max_cycle_len < 2:
            raise ValueError("max_cycle_len must be >= 2")
        needed = max(
            hard_repeat,
            no_change,
            consecutive_failure,
            max_cycle_len * oscillation_repeats,
        )
        if window < needed:
            raise ValueError(
                f"window ({window}) must be >= the widest check span ({needed})",
            )

        self._hard_repeat = hard_repeat
        self._soft_repeat = soft_repeat
        self._no_change = no_change
        self._consecutive_failure = consecutive_failure
        self._oscillation_repeats = oscillation_repeats
        self._max_cycle_len = max_cycle_len
        self._exempt_tools = exempt_tools

        self._tool_keys: deque[str | None] = deque(maxlen=window)
        self._obs_hashes: deque[str] = deque(maxlen=window)
        self._successes: deque[bool] = deque(maxlen=window)

    def reset(self) -> None:
        """Clear all history (e.g. when a new task begins in the same loop)."""
        self._tool_keys.clear()
        self._obs_hashes.clear()
        self._successes.clear()

    def record(self, step: StepObservation) -> StuckVerdict:
        """Record one round and return the resulting verdict.

        Checks run in priority order (most actionable first): hard same-tool
        repeat -> oscillation -> no-observable-change -> consecutive-failure,
        then the soft same-tool nudge. The first match wins.
        """
        self._tool_keys.append(step.tool_key)
        self._obs_hashes.append(step.observation_hash)
        self._successes.append(step.succeeded)

        base = _base_name(step.tool_key)
        if base is not None and base in self._exempt_tools:
            # Exempt no-op tools (wait/done/...) never trip the detector
            # (browser-use exempts {wait, done, go_back} entirely). The step is
            # still recorded above so it breaks an adjacent same-tool run.
            return StuckVerdict(stuck=False)
        has_tool = base is not None

        n_same = self._trailing_same_tool() if has_tool else 0
        n_nochange = self._trailing_no_change()
        n_fail = self._trailing_failures()

        if n_same >= self._hard_repeat:
            return self._abort(
                StuckReason.SAME_TOOL_REPEAT,
                f"LOOP DETECTED: you called the same action ('{base}') {n_same} "
                "times in a row without resolving the task. It will not advance "
                "now. Use a DIFFERENT tool, or emit [SELFFORK:DONE] if the goal "
                "is already met.",
                {"tool": base, "count": n_same, "threshold": self._hard_repeat},
            )

        cycle = self._oscillation() if has_tool else None
        if cycle is not None:
            cycle_len, repeats = cycle
            return self._abort(
                StuckReason.OSCILLATION,
                f"LOOP DETECTED: you are cycling between the same {cycle_len} "
                f"actions repeatedly ({repeats} cycles) with no progress. Break "
                "the pattern — try a genuinely different approach, or emit "
                "[SELFFORK:DONE] if the goal is met.",
                {"cycle_len": cycle_len, "repeats": repeats},
            )

        if n_nochange >= self._no_change:
            return self._abort(
                StuckReason.NO_OBSERVABLE_CHANGE,
                f"NO PROGRESS: the last {n_nochange} rounds produced no "
                "observable change. Re-think the approach, or emit "
                "[SELFFORK:DONE] if the goal is already met.",
                {"count": n_nochange, "threshold": self._no_change},
            )

        if n_fail >= self._consecutive_failure:
            return self._abort(
                StuckReason.CONSECUTIVE_FAILURE,
                f"REPEATED FAILURE: the last {n_fail} actions failed. The current "
                "approach is not working — change strategy, or ask the operator.",
                {"count": n_fail, "threshold": self._consecutive_failure},
            )

        if self._soft_repeat <= n_same < self._hard_repeat:
            return self._nudge(
                StuckReason.SAME_TOOL_REPEAT,
                f"NOTE: you have called '{base}' {n_same} times. If it is not "
                "making progress, switch to a different tool.",
                {"tool": base, "count": n_same, "soft_threshold": self._soft_repeat},
            )

        return StuckVerdict(stuck=False)

    # ── internals ───────────────────────────────────────────────────────────

    def _trailing_same_tool(self) -> int:
        """Count consecutive trailing rounds with the same (non-None) tool key."""
        if not self._tool_keys:
            return 0
        last = self._tool_keys[-1]
        if last is None:
            return 0
        count = 0
        for key in reversed(self._tool_keys):
            if key == last:
                count += 1
            else:
                break
        return count

    def _trailing_no_change(self) -> int:
        """Count consecutive trailing rounds with an identical observation hash."""
        if not self._obs_hashes:
            return 0
        last = self._obs_hashes[-1]
        count = 0
        for digest in reversed(self._obs_hashes):
            if digest == last:
                count += 1
            else:
                break
        return count

    def _trailing_failures(self) -> int:
        """Count consecutive trailing rounds whose tool action failed."""
        count = 0
        for ok in reversed(self._successes):
            if ok:
                break
            count += 1
        return count

    def _oscillation(self) -> tuple[int, int] | None:
        """Detect a repeating k-cycle in the recent tool keys.

        Returns ``(cycle_len, repeats)`` for the smallest cycle length ``k`` in
        ``2..max_cycle_len`` whose pattern repeats ``oscillation_repeats`` times
        at the tail and contains at least two distinct keys (a single-key cycle
        is the same-tool case, handled separately). ``None`` when no cycle.
        """
        keys = list(self._tool_keys)
        for cycle_len in range(2, self._max_cycle_len + 1):
            span = cycle_len * self._oscillation_repeats
            if len(keys) < span:
                continue
            tail = keys[-span:]
            pattern = tail[:cycle_len]
            bases = [_base_name(key) for key in pattern]
            if any(b is None or b in self._exempt_tools for b in bases):
                continue
            if len(set(pattern)) < 2:
                continue
            if all(tail[i] == pattern[i % cycle_len] for i in range(span)):
                return cycle_len, self._oscillation_repeats
        return None

    def _abort(
        self,
        reason: StuckReason,
        message: str,
        detail: dict[str, Any],
    ) -> StuckVerdict:
        return StuckVerdict(
            stuck=True,
            reason=reason,
            recovery=RecoveryAction.ABORT,
            corrective_message=message,
            detail=detail,
        )

    def _nudge(
        self,
        reason: StuckReason,
        message: str,
        detail: dict[str, Any],
    ) -> StuckVerdict:
        return StuckVerdict(
            stuck=False,
            reason=reason,
            recovery=RecoveryAction.NUDGE,
            corrective_message=message,
            detail=detail,
        )
