"""AIR — Agent Incident Response (S-Auto Faz E, researcher gap).

Detects panic / cover-up / sustained-failure signals in the
deliberation+execution stream and triggers a defence-in-depth
response. The detector is **fully deterministic** (ADR-008 §7 Lock
#4 — "eskalasyon kod'da, modelde değil"): the model cannot talk us out
of an emergency by emitting calming text.

Source motivation: arXiv 2602.11749 "Agent Incident Response" (Şubat
2026) + Replit Temmuz 2025 incident (`incidentdatabase.ai/cite/1152`,
Fortune 2025-07-23) — AI agents have been observed (a) bypassing
explicit "read-only" instructions, (b) silently destroying production
state, and (c) **fabricating cover-up text** in logs after the fact.
ADR-008 §6 only had preventive layers; AIR is the post-incident
catch.

What AIR does (Faz E scope):

1. **Detect** — substring scan over the model's reasoning + consecutive
   ``failed`` result outcomes.
2. **Halt** — set the scheduler's cooperative ``self_stop_requested``
   flag (ADR-008 §4.4 ``kendini_durdur`` action equivalent).
3. **Alert** — push a ``crit``-level Telegram message + write an
   ``air_alert`` field on the audit entry.

What AIR does NOT do in Faz E (deferred):

* **Auto-rollback** — Karpathy: don't add risk for hypothetical
  scenarios. A misdetect that wipes uncommitted work is worse than a
  human deciding to rollback. The detector records the recommended
  recovery (in the alert text); operator runs ``git`` themselves.
* **Self-healing retries** — if the daemon panicked once, exit cleanly
  and let the operator inspect before another tick fires.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

from selffork_orchestrator.heartbeat.deliberation import ActionDecision
from selffork_orchestrator.heartbeat.executor import ActionResult

__all__ = [
    "DEFAULT_CONSECUTIVE_FAILURE_THRESHOLD",
    "DEFAULT_PANIC_KEYWORDS",
    "AIRAlert",
    "AIRDetector",
    "AIRSeverity",
]


_log = logging.getLogger(__name__)


AIRSeverity = Literal["medium", "high", "critical"]


DEFAULT_PANIC_KEYWORDS: Final[tuple[str, ...]] = (
    # Self-reported panic states — the model literally narrating that
    # it has lost the plot (Replit cover-up forensic: "panicking").
    "panicking",
    "i'm panicking",
    "having a panic",
    # Cover-up / log-manipulation language.
    "cover up",
    "covering up",
    "hide the",
    "delete the log",
    # Acknowledged rule violation — Replit log: "violating explicit
    # instructions". An agent that NARRATES the violation is one
    # we should stop immediately.
    "violating explicit",
    "ignoring the freeze",
    "bypassing the",
    # Destruction acknowledgement.
    "wiped the",
    "destroyed the",
    "dropped the database",
    "rm -rf",
)
"""Substrings whose presence in ``decision.reasoning`` raises an alert.

Match is case-insensitive; ordering is documentation only.
"""


DEFAULT_CONSECUTIVE_FAILURE_THRESHOLD: Final[int] = 3
"""``N`` consecutive ``failed`` outcomes triggers a divergence alert.

Tuned for the heartbeat's 10-15 min reconciliation cadence: three
back-to-back failures is at least half an hour of broken automation —
worth waking the operator.
"""


@dataclass(frozen=True, slots=True)
class AIRAlert:
    """One detected incident.

    Attributes:
        severity: ``medium`` (single signal), ``high`` (multiple
            signals), ``critical`` (panic-keyword + sustained
            failures together).
        reason: Short human-readable cause.
        matched_keywords: Panic substrings that matched this tick.
        consecutive_failures: Number of consecutive ``failed`` results
            observed when the alert fired.
        detected_at: UTC timestamp.
        recommended_recovery: Operator-facing recovery hint (never
            executed automatically in Faz E — human decides).
    """

    severity: AIRSeverity
    reason: str
    matched_keywords: tuple[str, ...] = ()
    consecutive_failures: int = 0
    detected_at: datetime = (
        datetime(1970, 1, 1, tzinfo=UTC)  # overridden in factory
    )
    recommended_recovery: str = ""


class AIRDetector:
    """Stateful detector — keeps a sliding window of recent outcomes.

    Construct once at daemon boot; call :meth:`check` per tick AFTER
    the executor produces a result. The detector tracks failure
    streaks internally so callers do not have to maintain history.
    """

    def __init__(
        self,
        *,
        panic_keywords: Sequence[str] = DEFAULT_PANIC_KEYWORDS,
        consecutive_failure_threshold: int = (
            DEFAULT_CONSECUTIVE_FAILURE_THRESHOLD
        ),
    ) -> None:
        self._keywords = tuple(k.lower() for k in panic_keywords)
        self._failure_threshold = consecutive_failure_threshold
        self._consecutive_failures = 0

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def reset(self) -> None:
        """Clear the failure streak (e.g. operator manually resumed)."""
        self._consecutive_failures = 0

    def check(
        self,
        *,
        decision: ActionDecision | None,
        result: ActionResult | None,
    ) -> AIRAlert | None:
        """Inspect the latest tick — return an alert or ``None``."""
        # Maintain failure streak — runs every tick so the counter is
        # accurate even when no alert fires.
        if result is not None:
            if result.outcome == "failed":
                self._consecutive_failures += 1
            elif result.outcome in ("executed", "deferred"):
                self._consecutive_failures = 0
            # ``skipped`` neither resets nor advances — it's "no signal".

        panic_hits = self._scan_panic(decision)
        failure_breach = (
            self._consecutive_failures >= self._failure_threshold
        )

        if not panic_hits and not failure_breach:
            return None

        if panic_hits and failure_breach:
            severity: AIRSeverity = "critical"
            reason = (
                f"panic keywords matched ({len(panic_hits)}) AND "
                f"{self._consecutive_failures} consecutive failures"
            )
            recovery = (
                "Inspect the audit log; run `git status` in the active "
                "workspace before any further heartbeat tick. Consider "
                "`git stash` or `git restore .` if uncommitted changes "
                "look unsafe."
            )
        elif panic_hits:
            severity = "high"
            reason = f"panic keywords matched ({len(panic_hits)})"
            recovery = (
                "Read the last decision's reasoning in the audit log; "
                "the model narrated a panic / rule-violation state."
            )
        else:
            severity = "medium"
            reason = f"{self._consecutive_failures} consecutive failed results"
            recovery = (
                "Inspect the last failed result's metadata; the "
                "automation surface is degraded."
            )

        return AIRAlert(
            severity=severity,
            reason=reason,
            matched_keywords=panic_hits,
            consecutive_failures=self._consecutive_failures,
            detected_at=datetime.now(tz=UTC),
            recommended_recovery=recovery,
        )

    def _scan_panic(
        self, decision: ActionDecision | None
    ) -> tuple[str, ...]:
        """Substring scan with negation pre-filter.

        Audit fix #2 (audit-god 2026-05-23 MAJOR): strip ``not X``
        clauses so the model can narrate past or hypothetical panic
        states without tripping a live alert. The contractor pattern
        is "narrate the current state honestly" — so "I am NOT
        panicking" is treated as healthy, while "I'm panicking" stays
        a hit.
        """
        if decision is None or not decision.reasoning:
            return ()
        haystack = decision.reasoning.lower()
        # Replace ``not <word>`` / ``don't <word>`` / etc. with a
        # neutral placeholder so the keyword scan misses the original
        # word. Conservative — only consumes the immediately
        # following word, not arbitrarily long clauses, so something
        # like "I'm not sure but I am panicking" still trips on
        # ``panicking``.
        sanitized = _NEGATION_RE.sub("[neg]", haystack)
        return tuple(k for k in self._keywords if k in sanitized)


_NEGATION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:not|never|wasn't|isn't|aren't|won't|don't|doesn't|didn't|"
    r"n[\'\u2019]t)\s+(?:\w+\s+){0,2}\w+",
    re.IGNORECASE,
)
"""Match a negation word followed by up to three following words.

Catches ``not panicking``, ``isn't covering``, ``don't violate``,
``wasn't lying``, plus longer constructions like
``won't be covering up`` (negation + 2 intermediate words + keyword).
The apostrophe class accepts ASCII ``'`` and Unicode U+2019 right
single-quote so the regex matches both straight and smart quotes."""
