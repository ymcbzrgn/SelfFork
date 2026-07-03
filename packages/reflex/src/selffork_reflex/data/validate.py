"""S-Train item T5 -- corpus validator (deterministic, no model, CI-runnable).

Validates the corpus JSONL artifact that T2 (:mod:`.assemble`) produces and T4
(``selffork train --dataset auto``) writes. Fails loudly on the corruption
modes the S-Train smoke gate names (``docs/plans/S-Train_Smoke_Checklist.md``
item T5): a bad loss mask, a missing/unknown source, or schema drift. Also
*flags* (warning, not error) the agentic-trace-length distribution against the
ADR-010 section 2.3 "30+ tools/session" target, so short-trace corpora surface
for review without failing an otherwise-valid small corpus.

Pure over already-parsed rows (:func:`validate_corpus_rows`) with a thin file
glue (:func:`validate_corpus_file`) and a ``main()`` for a CI hook. Imports only
its sibling :mod:`.normalize` / :mod:`.assemble` constants, so ``selffork-reflex``
stays dependency-free.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from selffork_reflex.data.assemble import SOURCE_PRECEDENCE
from selffork_reflex.data.normalize import (
    INACTIVE_WEIGHT,
    PRIOR_OPERATOR_WEIGHT,
    TARGET_OPERATOR_WEIGHT,
)

__all__ = [
    "AGENTIC_TRACE_TOOL_TARGET",
    "KNOWN_SOURCES",
    "VALID_ROLES",
    "ValidationReport",
    "validate_corpus_file",
    "validate_corpus_rows",
]

VALID_ROLES: frozenset[str] = frozenset({"system", "operator", "assistant", "tool", "context"})
KNOWN_SOURCES: frozenset[str] = frozenset(SOURCE_PRECEDENCE)
# ADR-010 section 2.3: the corpus must carry long multi-tool agentic traces
# (30+ tools/session) so Self Jr learns *when* to plan vs act.
AGENTIC_TRACE_TOOL_TARGET = 30


@dataclass
class ValidationReport:
    """Outcome of validating a corpus.

    ``errors`` are hard failures (a corrupt/invalid corpus -> :attr:`ok` False);
    ``warnings`` are advisory (e.g. the agentic-trace distribution missing the
    30-tool target). ``tool_counts`` is the per-sample tool-message count, the
    raw material for the agentic-trace distribution flag.
    """

    sample_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tool_counts: list[int] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def agentic_trace_max(self) -> int:
        return max(self.tool_counts, default=0)

    @property
    def agentic_trace_target_hits(self) -> int:
        return sum(1 for c in self.tool_counts if c >= AGENTIC_TRACE_TOOL_TARGET)


def _validate_message(where: str, msg: object, errors: list[str]) -> str | None:
    """Validate one message mapping; return its role (str) or ``None`` on error."""
    if not isinstance(msg, Mapping):
        errors.append(f"{where}: message must be an object, got {type(msg).__name__}")
        return None
    role = msg.get("role")
    if role not in VALID_ROLES:
        errors.append(f"{where}: role {role!r} not in {sorted(VALID_ROLES)}")
        role = None
    if not isinstance(msg.get("content"), str):
        errors.append(f"{where}: content must be a string")
    weight = msg.get("loss_weight")
    if not isinstance(weight, (int, float)) or isinstance(weight, bool):
        errors.append(f"{where}: loss_weight must be a number, got {weight!r}")
    return role if isinstance(role, str) else None


def _expected_weight(role: str, *, is_target: bool) -> float:
    if is_target:
        return TARGET_OPERATOR_WEIGHT
    if role == "operator":
        return PRIOR_OPERATOR_WEIGHT
    return INACTIVE_WEIGHT


def _validate_row(index: int, row: object, report: ValidationReport) -> None:
    where = f"sample[{index}]"
    if not isinstance(row, Mapping):
        report.errors.append(f"{where}: not an object")
        return

    # ---- schema: required keys + types -----------------------------------
    session_id = row.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        report.errors.append(f"{where}: session_id must be a non-empty string")

    source = row.get("source")
    if source not in KNOWN_SOURCES:
        report.errors.append(
            f"{where}: source {source!r} not in known sources "
            f"{sorted(KNOWN_SOURCES)} (missing/unknown attribution)"
        )

    messages = row.get("messages")
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        report.errors.append(f"{where}: messages must be a list")
        return
    if not messages:
        report.errors.append(f"{where}: messages must be non-empty")
        return

    target_index = row.get("target_index")
    last = len(messages) - 1
    if target_index != last:
        report.errors.append(
            f"{where}: target_index {target_index!r} must be the last message index ({last})"
        )

    # ---- per-message schema + loss-mask integrity ------------------------
    roles: list[str | None] = []
    for i, msg in enumerate(messages):
        roles.append(_validate_message(f"{where}.messages[{i}]", msg, report.errors))

    tool_count = sum(1 for r in roles if r == "tool")
    report.tool_counts.append(tool_count)

    # First message must be the system framing at weight 0.0.
    if roles and roles[0] != "system":
        report.errors.append(f"{where}: first message must be role 'system'")

    # Exactly one target message (weight 1.0), and it must be the last one and
    # an operator turn.
    target_weight_hits = 0
    for i, msg in enumerate(messages):
        if not isinstance(msg, Mapping):
            continue
        role = roles[i]
        weight = msg.get("loss_weight")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            continue
        is_target = i == last
        if weight == TARGET_OPERATOR_WEIGHT:
            target_weight_hits += 1
        if role is None:
            continue
        expected = _expected_weight(role, is_target=is_target)
        if weight != expected:
            report.errors.append(
                f"{where}.messages[{i}]: role {role!r} "
                f"{'(target) ' if is_target else ''}must have loss_weight "
                f"{expected}, got {weight}"
            )
        if is_target and role != "operator":
            report.errors.append(f"{where}: target message role must be 'operator', got {role!r}")

    if target_weight_hits != 1:
        report.errors.append(
            f"{where}: expected exactly one target message at loss_weight "
            f"{TARGET_OPERATOR_WEIGHT}, found {target_weight_hits}"
        )


def validate_corpus_rows(rows: Sequence[object]) -> ValidationReport:
    """Validate already-parsed corpus rows. Pure; never raises on bad data."""
    report = ValidationReport(sample_count=len(rows))
    if not rows:
        report.errors.append("corpus is empty (no samples)")
        return report
    for index, row in enumerate(rows):
        _validate_row(index, row, report)

    # Agentic-trace distribution flag (advisory, ADR-010 section 2.3).
    if report.agentic_trace_max < AGENTIC_TRACE_TOOL_TARGET:
        report.warnings.append(
            f"agentic-trace target not met: no sample reaches "
            f"{AGENTIC_TRACE_TOOL_TARGET}+ tool messages "
            f"(max seen={report.agentic_trace_max}); corpus is short on long "
            "multi-tool traces (ADR-010 section 2.3)"
        )
    return report


def validate_corpus_file(path: str | Path) -> ValidationReport:
    """Parse a corpus JSONL file then :func:`validate_corpus_rows`.

    A malformed JSON line is a hard error (recorded, not raised); a missing file
    is reported as a single error so a CI hook fails cleanly.
    """
    p = Path(path)
    if not p.is_file():
        return ValidationReport(errors=[f"corpus file not found: {p}"])
    rows: list[object] = []
    line_errors: list[str] = []
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            line_errors.append(f"line {lineno}: invalid JSON ({exc})")
    if line_errors:
        report = ValidationReport(errors=line_errors)
        report.sample_count = len(rows)
        return report
    return validate_corpus_rows(rows)


def main(argv: Sequence[str] | None = None) -> int:
    """CI hook: ``python -m selffork_reflex.data.validate <corpus.jsonl>``."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: validate.py <corpus.jsonl>", file=sys.stderr)
        return 2
    report = validate_corpus_file(args[0])
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if not report.ok:
        print(f"Corpus INVALID ({len(report.errors)} errors):", file=sys.stderr)
        for err in report.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(
        f"Corpus OK ({report.sample_count} samples; "
        f"{report.agentic_trace_target_hits} reach the "
        f"{AGENTIC_TRACE_TOOL_TARGET}-tool agentic-trace target)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
