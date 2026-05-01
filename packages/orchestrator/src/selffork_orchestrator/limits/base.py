"""LimitDetector ABC + verdict types — subscription rate-limit detection.

Per ``feedback_infra_before_finetune.md``, SelfFork tracks subscription
quotas (Claude Pro/Max, Google login tier, opencode-routed providers)
across the round loop. After each CLI exec, the orchestrator passes the
captured (stdout, stderr, exit_code) tuple to a CLI-specific
:class:`LimitDetector`. The detector returns a :class:`LimitVerdict`:

- :class:`NoLimit` — keep going.
- :class:`RateLimited` — quota hit, schedule a resume at ``reset_at``.
- :class:`AuthRequired` — re-login needed, fail fast and ask user.

Per-CLI detectors live in sibling modules
(``claude_detector.py`` etc.) and are wired through
:func:`build_limit_detector` (factory).

Research basis: 3 selffork-researcher reports on 2026-05-01:
- claude: ``--output-format stream-json`` carries an ``error`` enum
  (``rate_limit | authentication_failed | server_error |
  billing_error | invalid_request | max_output_tokens | ...``);
  text fallback regex on ``"Claude usage limit reached. Your limit
  will reset at <H><am|pm> (<IANA-tz>)"``.
- gemini: stderr regex (``--output-format json`` is buggy in 0.39.x);
  RPM ``"Please retry in <s>s"``, RPD ``"Access resets at <H>:<M>
  AM/PM GMT[+-]X"``, fallback to midnight Pacific.
- opencode: stderr regex with NON-Claude provider patterns only
  (Claude routes through ``claude`` CLI per ``project_cli_provider_routing.md``).

See: ``docs/decisions/ADR-001_MVP_v0.md`` §17 (Faz B extension).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "AuthRequired",
    "LimitDetector",
    "LimitVerdict",
    "NoLimit",
    "RateLimited",
]


@dataclass(frozen=True, slots=True)
class NoLimit:
    """No subscription limit issue detected. Caller should keep running."""


@dataclass(frozen=True, slots=True)
class RateLimited:
    """Quota / rate-limit hit. Caller should pause and schedule a resume.

    Attributes:
        reset_at: timezone-aware datetime when the limit window opens
            again. Always UTC-normalized at construction so callers can
            compare against ``datetime.now(timezone.utc)`` directly.
        reason: human-readable summary (kept short — for logs and the
            scheduled-resume record).
        kind: subcategory hint. ``"rpm"`` short window (seconds),
            ``"rpd"`` daily, ``"weekly"`` Claude weekly cap,
            ``"unknown"`` if the detector couldn't classify.
    """

    reset_at: datetime
    reason: str
    kind: str = "unknown"


@dataclass(frozen=True, slots=True)
class AuthRequired:
    """Auth (login session) is invalid or expired. User must re-login.

    Attributes:
        reason: short human-readable message; the orchestrator surfaces
            it verbatim with a "run `selffork auth <cli>`" hint.
    """

    reason: str


LimitVerdict = NoLimit | RateLimited | AuthRequired


class LimitDetector(ABC):
    """Adapter contract: classify a CLI agent's exit into a verdict."""

    @abstractmethod
    def detect(
        self,
        *,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> LimitVerdict:
        """Inspect captured output and exit code; return a verdict.

        Implementations MUST be deterministic and side-effect-free —
        the orchestrator decides whether to persist the verdict, log
        it, or react to it.
        """
