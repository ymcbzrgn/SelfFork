"""UsageAggregator — derive per-provider usage from on-disk audit logs.

Walks every configured audit directory + every project's audit dir,
counts ``agent.invoke`` events per inferred CLI binary, and recovers
the next reset moment from any ``agent.rate_limited`` events
(payload ``resume_at_iso``) or :class:`ScheduledResumeStore` records
that name the same CLI.

Window choices are deliberate:

| CLI            | Window | Why |
|----------------|--------|-----|
| claude-code    | 5h     | Pro/Max 5-hour rolling subscription window |
| gemini-cli     | 24h    | RPD reset at midnight Pacific (best dashboard signal) |
| opencode       | 1h     | Generic provider-agnostic short window |
| codex          | 1h     | Stub — same as opencode for now |

If a CLI never appears in audit logs, it doesn't get a row — we never
fabricate "0 calls in 5h" entries (per
``project_provider_usage_source.md``).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from selffork_orchestrator.dashboard.audit_reader import _infer_cli_from_binary
from selffork_orchestrator.resume.store import ScheduledResumeStore
from selffork_orchestrator.usage.model import ProviderName, ProviderUsage
from selffork_shared.logging import get_logger

__all__ = ["UsageAggregator", "UsageAggregatorConfig"]

_log = get_logger(__name__)

# Window per CLI in seconds.
_WINDOWS: dict[ProviderName, tuple[str, int]] = {
    "claude-code": ("5h", 5 * 3600),
    "gemini-cli": ("24h", 24 * 3600),
    "opencode": ("1h", 3600),
    "codex": ("1h", 3600),
}


@dataclass(frozen=True, slots=True)
class UsageAggregatorConfig:
    """Where to look for audit logs.

    Attributes:
        audit_dirs: every directory whose ``*.jsonl`` files should be
            walked. Typically the global ``~/.selffork/audit/`` plus
            each project's ``~/.selffork/projects/<slug>/audit/``.
        resume_store: the active store; we read its records to recover
            ``next_reset_at`` for paused sessions.
        now: the wall-clock moment used for windowing — injectable for
            deterministic tests.
    """

    audit_dirs: tuple[Path, ...]
    resume_store: ScheduledResumeStore | None
    now: datetime | None = None


class UsageAggregator:
    """Reads audit logs and emits :class:`ProviderUsage` rows."""

    def __init__(self, config: UsageAggregatorConfig) -> None:
        self._config = config

    def aggregate(self) -> list[ProviderUsage]:
        now = self._config.now or datetime.now(UTC)
        # Per-CLI counters keyed by ProviderName.
        counts: dict[ProviderName, int] = {}
        last_rate_limited: dict[ProviderName, datetime | None] = {}
        next_reset_from_audit: dict[ProviderName, datetime | None] = {}

        for path in _iter_jsonl_files(self._config.audit_dirs):
            try:
                _walk_jsonl(
                    path=path,
                    now=now,
                    counts=counts,
                    last_rate_limited=last_rate_limited,
                    next_reset_from_audit=next_reset_from_audit,
                )
            except OSError as exc:
                _log.info(
                    "usage_skip_unreadable_audit",
                    path=str(path),
                    reason=str(exc),
                )

        # Add resets from the resume store too — those are the
        # authoritative future moments per CLI.
        next_reset_from_resume: dict[ProviderName, datetime] = {}
        if self._config.resume_store is not None:
            try:
                records = self._config.resume_store.list_all()
            except OSError:
                records = []
            for record in records:
                cli = _validate_cli_name(record.cli_agent)
                if cli is None:
                    continue
                # Only future records carry meaning here.
                if record.resume_at <= now:
                    continue
                prev = next_reset_from_resume.get(cli)
                if prev is None or record.resume_at < prev:
                    next_reset_from_resume[cli] = record.resume_at

        out: list[ProviderUsage] = []
        for cli, n in counts.items():
            label, window_seconds = _WINDOWS[cli]
            # Prefer the earliest known future reset between audit-
            # derived and resume-store-derived sources.
            candidates: list[datetime] = []
            audit_reset = next_reset_from_audit.get(cli)
            if audit_reset is not None and audit_reset > now:
                candidates.append(audit_reset)
            resume_reset = next_reset_from_resume.get(cli)
            if resume_reset is not None:
                candidates.append(resume_reset)
            next_reset = min(candidates) if candidates else None
            out.append(
                ProviderUsage(
                    cli_agent=cli,
                    window_label=label,
                    window_seconds=window_seconds,
                    calls_in_window=n,
                    next_reset_at=next_reset,
                    last_rate_limited_at=last_rate_limited.get(cli),
                ),
            )
        out.sort(key=lambda u: u.cli_agent)
        return out


def _iter_jsonl_files(dirs: Iterable[Path]) -> Iterable[Path]:
    for d in dirs:
        if not d.is_dir():
            continue
        for entry in sorted(d.iterdir()):
            if entry.is_file() and entry.suffix == ".jsonl":
                yield entry


def _walk_jsonl(
    *,
    path: Path,
    now: datetime,
    counts: dict[ProviderName, int],
    last_rate_limited: dict[ProviderName, datetime | None],
    next_reset_from_audit: dict[ProviderName, datetime | None],
) -> None:
    """Single-pass scan; updates all dicts in place."""
    # Any session whose first invoke binary we've seen — we use it to
    # attribute later events in the same file (rate_limited events
    # don't carry a binary, only the parent session's CLI does).
    file_cli: ProviderName | None = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            obj = _parse_line(line)
            if obj is None:
                continue
            ts = _parse_iso(obj.get("ts"))
            cat = obj.get("category")
            payload = obj.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}

            if cat == "agent.invoke" or cat == "sandbox.exec":
                cli = _cli_from_invoke(payload)
                if cli is not None:
                    file_cli = cli
                    if (
                        cat == "agent.invoke"
                        and ts is not None
                        and (now - ts).total_seconds() <= _WINDOWS[cli][1]
                    ):
                        counts[cli] = counts.get(cli, 0) + 1
            elif cat == "agent.rate_limited":
                if file_cli is None:
                    continue
                if ts is not None:
                    prev = last_rate_limited.get(file_cli)
                    if prev is None or ts > prev:
                        last_rate_limited[file_cli] = ts
                resume_at = _parse_iso(payload.get("resume_at_iso"))
                if resume_at is not None and resume_at > now:
                    prev_reset = next_reset_from_audit.get(file_cli)
                    if prev_reset is None or resume_at < prev_reset:
                        next_reset_from_audit[file_cli] = resume_at


def _parse_line(line: str) -> dict[str, object] | None:
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _parse_iso(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    s = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _cli_from_invoke(payload: dict[str, object]) -> ProviderName | None:
    binary = payload.get("binary")
    if isinstance(binary, str):
        name = _infer_cli_from_binary(binary)
        return _validate_cli_name(name)
    cmd = payload.get("command")
    if isinstance(cmd, list) and cmd and isinstance(cmd[0], str):
        return _validate_cli_name(_infer_cli_from_binary(cmd[0]))
    return None


def _validate_cli_name(name: object) -> ProviderName | None:
    if not isinstance(name, str):
        return None
    # Narrowing the literal Mapping check requires an explicit branch
    # per name; the dict's keys are exactly the four ProviderName values.
    if name == "claude-code":
        return "claude-code"
    if name == "gemini-cli":
        return "gemini-cli"
    if name == "opencode":
        return "opencode"
    if name == "codex":
        return "codex"
    return None
