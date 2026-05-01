"""SPAWN sentinel parser — extract child-spawn requests from a Jr reply.

Per the Faz A design (``project_yamac_jr_drives_3_cli_agents.md`` +
``feedback_infra_before_finetune.md``), SelfFork Jr can supervise
multiple parallel child sessions by emitting one or more
``[SELFFORK:SPAWN: <work-spec>]`` markers in its reply.

Format
------

    [SELFFORK:SPAWN: <free-text spec>]

The spec is the body the orchestrator hands to the child as its PRD.
Free-form Turkish or English; can span multiple words but cannot
contain a literal ``]`` (we stop at the first close bracket per tag).
Multiple SPAWN tags in one reply spawn N children in parallel.

Coexistence with DONE
---------------------

If the same reply contains BOTH a SPAWN tag and the DONE sentinel
(``[SELFFORK:DONE]``), the orchestrator treats it as DONE first —
i.e., terminate without spawning. Rationale: a final reply that says
"task X is complete; ALSO spawn this cleanup" is ambiguous, and the
safer interpretation is "the user wants to finish."  Detection of
this case is left to the caller (this module just extracts SPAWNs).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["SpawnRequest", "extract_spawn_requests"]


# Greedy-but-stops-at-first-``]`` match. ``\s*`` after ``SPAWN:`` so the
# space is optional, and we strip leading/trailing whitespace from the
# captured spec.
_SPAWN_RE = re.compile(
    r"\[SELFFORK:SPAWN:\s*([^\]]+)\]",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SpawnRequest:
    """One parsed ``[SELFFORK:SPAWN: ...]`` request.

    Attributes:
        index: zero-based position in the parent reply (0 = first SPAWN).
            Used for stable child IDs and pane labels.
        spec: the free-text body Jr asked to delegate. Stripped of
            surrounding whitespace.
    """

    index: int
    spec: str


def extract_spawn_requests(reply: str) -> list[SpawnRequest]:
    """Parse a Jr reply, returning every ``SELFFORK:SPAWN`` request in order.

    Empty, whitespace-only, or absent SPAWN tags yield an empty list.
    Malformed tags (no closing bracket) are silently skipped — Jr is a
    small model and we'd rather drop noise than crash the loop.

    The function is deterministic and side-effect-free; it does NOT
    decide whether SPAWN should win or lose against a coexisting DONE
    sentinel — that's the run-loop's job.
    """
    out: list[SpawnRequest] = []
    for i, match in enumerate(_SPAWN_RE.finditer(reply)):
        spec = match.group(1).strip()
        if not spec:
            continue
        out.append(SpawnRequest(index=i, spec=spec))
    return out
