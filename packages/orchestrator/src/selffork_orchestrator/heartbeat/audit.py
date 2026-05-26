"""Heartbeat audit log — perceive→decide→act→record per tick (S-Auto Faz E).

ADR-008 §6 safety layer #4: *"Her karar denetlenir — görülen durum +
yasal küme + seçilen eylem + gerekçe + sonuç Mind'a/audit'e yazılır."*
Faz E writes the canonical record; later sprints (Mind pillar
implementation) attach reflection / RAG layers on top.

Wire format:

* **JSONL** at ``~/.selffork/heartbeat/audit.jsonl`` (default; operator
  overrides through :class:`AuditWriter` ``root`` kwarg).
* One line per tick (pydantic ``model_dump_json``).
* Append-only — never rewrites; replays reconstruct state from the
  full log.

Idempotency (ADR-008 §6 madde 4): each tick carries a structural key
``(tick, action, project_slug)`` so reading the log + dedupe-by-key
yields a clean event stream. Faz E records the key; Mind compaction
(later sprint) dedupes.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from selffork_orchestrator.heartbeat.deliberation import ActionDecision
from selffork_orchestrator.heartbeat.executor import ActionResult
from selffork_orchestrator.heartbeat.filter import WorldState

__all__ = [
    "AuditEntry",
    "AuditWriter",
    "Correction",
    "build_audit_entry",
    "default_audit_path",
    "default_corrections_path",
]


_log = logging.getLogger(__name__)


class AuditEntry(BaseModel):
    """One row in the heartbeat audit log — frozen + JSON-friendly."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tick: int = Field(ge=0)
    timestamp: datetime
    trigger: str
    world_state: dict[str, Any] = Field(default_factory=dict)
    legal_actions: list[str] = Field(default_factory=list)
    decision_action: str | None = None
    decision_reasoning: str | None = None
    decision_fallback: bool | None = None
    # ADR-011 §3.4 — True when the fallback WAIT was caused by a slow /
    # wedged model (idle-token watchdog or per-tick budget), distinct from
    # an unreachable/unparseable model. Lets a feed/replay surface "the
    # loop stayed alive through a slow tick" without conflating causes.
    decision_stalled: bool | None = None
    result_action: str | None = None
    result_outcome: str | None = None
    result_summary: str | None = None
    result_metadata: dict[str, Any] = Field(default_factory=dict)
    air_alert: str | None = None
    idempotency_key: str | None = None

    def as_jsonl(self) -> str:
        """Serialize for append — newline-delimited JSON, one line."""
        return self.model_dump_json() + "\n"


def default_audit_path() -> Path:
    """Default location: ``~/.selffork/heartbeat/audit.jsonl``."""
    return Path("~/.selffork/heartbeat/audit.jsonl").expanduser()


def default_corrections_path() -> Path:
    """Default location: sibling of :func:`default_audit_path`.

    Resolves to ``~/.selffork/heartbeat/corrections.jsonl`` today (kept in
    lock-step with the audit path via :meth:`Path.with_name` so a future
    relocation of :func:`default_audit_path` carries this sibling along
    instead of silently drifting). The coaching-loop record (ADR-010
    §coaching, S-Vision Faz D) lives in its own append-only JSONL so the
    operator's correction history can be diffed against the
    :class:`AuditEntry` stream without schema mixing.
    """
    return default_audit_path().with_name("corrections.jsonl")


class Correction(BaseModel):
    """Operator coaching record — an explicit "this decision was wrong" event.

    ADR-010 §coaching / S-Vision Faz D. Each :class:`Correction` references
    a prior :class:`AuditEntry` by its ``idempotency_key`` and carries the
    operator's free-text correction plus an optional ``suggested_action``
    label. S-Train later uses these as high-weight reflex examples
    ("operator over the model").

    Append-only by design — the audit log never rewrites, so a correction
    is a NEW record next to the original entry, not an in-place edit.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    audit_idempotency_key: str
    correction_text: str
    suggested_action: str | None = None
    corrected_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    source: str = "operator"

    def as_jsonl(self) -> str:
        """Serialize for append — newline-delimited JSON, one line."""
        return self.model_dump_json() + "\n"


@dataclass(frozen=True, slots=True)
class AuditWriter:
    """Append :class:`AuditEntry` rows to disk (sync, atomic-per-line).

    Construct once at daemon boot. The writer is intentionally sync —
    one line per tick at most every ``tick_seconds`` is well below the
    asyncio-blocking threshold (file I/O measured in milliseconds);
    skipping the thread-pool round-trip keeps the daemon snappy on
    shutdown.
    """

    path: Path

    def write(self, entry: AuditEntry) -> None:
        """Atomically append one entry. Creates parent dir on demand."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = entry.as_jsonl()
        with self.path.open("a", encoding="utf-8") as fp:
            fp.write(line)

    def read_all(self) -> Iterator[AuditEntry]:
        """Iterate every entry on disk; skip malformed lines (defensive)."""
        if not self.path.is_file():
            return
        with self.path.open("r", encoding="utf-8") as fp:
            for raw in fp:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                    yield AuditEntry.model_validate(payload)
                except (json.JSONDecodeError, ValueError):
                    _log.warning(
                        "heartbeat_audit_replay_malformed_line",
                        extra={"path": str(self.path)},
                    )

    @property
    def corrections_path(self) -> Path:
        """Sibling JSONL where :class:`Correction` rows append (ADR-010 §coaching).

        Derived from :attr:`path` so a custom audit location keeps its
        coaching trail next door (e.g. per-test ``tmp_path``).
        """
        return self.path.with_name("corrections.jsonl")

    def write_correction(self, correction: Correction) -> None:
        """Atomically append one :class:`Correction`. Creates parent dir on demand.

        Append-only mirrors :meth:`write` — corrections never rewrite an
        :class:`AuditEntry`; S-Train + Mind compaction stitch the original
        record and its corrections by ``audit_idempotency_key``.
        """
        self.corrections_path.parent.mkdir(parents=True, exist_ok=True)
        line = correction.as_jsonl()
        with self.corrections_path.open("a", encoding="utf-8") as fp:
            fp.write(line)

    def read_corrections(self) -> Iterator[Correction]:
        """Iterate every :class:`Correction` on disk; skip malformed lines."""
        if not self.corrections_path.is_file():
            return
        with self.corrections_path.open("r", encoding="utf-8") as fp:
            for raw in fp:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                    yield Correction.model_validate(payload)
                except (json.JSONDecodeError, ValueError):
                    _log.warning(
                        "heartbeat_audit_corrections_malformed_line",
                        extra={"path": str(self.corrections_path)},
                    )

    @classmethod
    def default(cls) -> AuditWriter:
        """Construct against :func:`default_audit_path`."""
        return cls(path=default_audit_path())


def build_audit_entry(
    *,
    tick: int,
    trigger: str,
    world_state: WorldState,
    legal_actions: frozenset[str] | None = None,
    decision: ActionDecision | None = None,
    result: ActionResult | None = None,
    air_alert: str | None = None,
) -> AuditEntry:
    """Compose an :class:`AuditEntry` from the per-tick inputs.

    Pulls only the WorldState fields the audit log surfaces (the model
    sees the *full* state via prompts; the audit log keeps a compact
    projection so the file stays small on long-running daemons).
    """
    state_dict: dict[str, Any] = {
        "pause_active": world_state.pause_active,
        "within_active_hours": world_state.within_active_hours,
        "active_concurrent_sessions": world_state.active_concurrent_sessions,
        "max_concurrent_sessions": world_state.max_concurrent_sessions,
        "creative_mode_enabled": world_state.creative_mode_enabled,
        "supervised_mode": world_state.supervised_mode,
        "last_active_workspace": world_state.last_active_workspace,
    }
    quota_summary: dict[str, Any] = {}
    for cli_id, snap in world_state.cli_quota.items():
        if snap is None:
            quota_summary[cli_id] = None
            continue
        quota_summary[cli_id] = {
            "exhausted": snap.is_exhausted(
                world_state.quota_exhaustion_threshold_pct
            ),
            "captured_at": snap.captured_at.isoformat(),
            "max_pct": (
                max(w.used_pct for w in snap.windows.values())
                if snap.windows
                else None
            ),
        }
    state_dict["cli_quota"] = quota_summary

    decision_action = decision.action.value if decision is not None else None
    project_slug = world_state.last_active_workspace
    idempotency_key = (
        f"{tick}:{decision_action or 'noop'}:{project_slug or 'global'}"
    )
    return AuditEntry(
        tick=tick,
        timestamp=datetime.now(tz=UTC),
        trigger=trigger,
        world_state=state_dict,
        legal_actions=sorted(legal_actions) if legal_actions else [],
        decision_action=decision_action,
        decision_reasoning=decision.reasoning if decision is not None else None,
        decision_fallback=(
            decision.fallback if decision is not None else None
        ),
        decision_stalled=(
            decision.stalled if decision is not None else None
        ),
        result_action=result.action.value if result is not None else None,
        result_outcome=result.outcome if result is not None else None,
        result_summary=result.summary if result is not None else None,
        result_metadata=dict(result.metadata) if result is not None else {},
        air_alert=air_alert,
        idempotency_key=idempotency_key,
    )
