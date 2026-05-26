"""Heartbeat audit.jsonl → T2 Episodic ingest pipeline (ADR-009 §5).

Connects S-Auto Faz E's ``~/.selffork/heartbeat/audit.jsonl`` (and its
sibling ``corrections.jsonl``, S-Bridge) to the Mind pillar's T2
Episodic tier. Each heartbeat tick becomes one ``observation`` Note
(the canonical record); each operator correction becomes one
``decision`` Note with high importance (operator coaching).

Design:

- **Structured-source bypass (Cognee pattern, ADR-002 §5).** No LLM
  extraction — heartbeat entries are already typed; we project them 1:1
  into Notes.

- **Idempotent.** Each audit entry carries ``idempotency_key``
  (S-Auto Faz E); we reuse it as the Note's ``content_hash`` so re-ingest
  of the same audit log resolves to the same UUID5 identity and the
  ``MindStore.upsert_note`` ON CONFLICT path collapses to a no-op.

- **Checkpoint.** The offset of the last successfully-ingested line is
  persisted to ``<heartbeat>/ingest-checkpoint.json`` (atomic temp+rename
  pattern, ADR-008 §6) so restart resumes where it left off without
  reading the whole file.

- **Tail-follow.** :meth:`HeartbeatIngester.run` loops with a small sleep
  between scans; new lines appended to the audit log are picked up on the
  next iteration. Shutdown is cooperative — call :meth:`stop` from another
  task and the run loop exits on the next iteration.

- **PROJECT pool routing.** The ``project_slug`` is read from each entry's
  ``world_state.last_active_workspace``; entries without an active project
  are written to the GLOBAL pool's ``g:global`` partition (operator-level
  events that aren't bound to a single project).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Iterable, Iterator
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from selffork_mind.memory.model import Note, compute_content_hash
from selffork_mind.store.base import (
    GLOBAL_GROUP_ID,
    MindStore,
    derive_group_id,
)

__all__ = [
    "CorrectionIngester",
    "HeartbeatIngestReport",
    "HeartbeatIngester",
    "IngestCheckpoint",
    "audit_entry_to_note",
    "correction_entry_to_note",
]


_log = logging.getLogger(__name__)


# ── checkpoint persistence ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IngestCheckpoint:
    """Offset cursor into the audit log.

    ``last_byte_offset`` is the byte position just past the last successfully
    ingested line. ``last_tick`` is the tick number of that line (for
    operator-facing diagnostics; not used for resume decisions).

    ``last_ingested_at`` is wall-clock time of the most recent successful
    flush; surfaces "ingester is alive" in admin views without depending
    on the audit log's own timestamps.
    """

    last_byte_offset: int = 0
    last_tick: int | None = None
    last_ingested_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "last_byte_offset": self.last_byte_offset,
            "last_tick": self.last_tick,
            "last_ingested_at": (
                self.last_ingested_at.isoformat() if self.last_ingested_at else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> IngestCheckpoint:
        offset_raw = data.get("last_byte_offset", 0)
        offset = int(offset_raw) if isinstance(offset_raw, (int, float, str)) else 0
        tick_raw = data.get("last_tick")
        tick: int | None
        if isinstance(tick_raw, (int, float, str)) and tick_raw is not None:
            tick = int(tick_raw)
        else:
            tick = None
        ts_raw = data.get("last_ingested_at")
        ts: datetime | None = None
        if isinstance(ts_raw, str):
            with suppress(ValueError):
                ts = datetime.fromisoformat(ts_raw)
        return cls(last_byte_offset=offset, last_tick=tick, last_ingested_at=ts)


def _load_checkpoint(path: Path) -> IngestCheckpoint:
    if not path.is_file():
        return IngestCheckpoint()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _log.warning("ingest_checkpoint_load_failed path=%s", path)
        return IngestCheckpoint()
    if not isinstance(data, dict):
        return IngestCheckpoint()
    return IngestCheckpoint.from_dict(data)


def _save_checkpoint(path: Path, checkpoint: IngestCheckpoint) -> None:
    """Atomic write — temp file + os.replace (S-Auto Faz E pattern)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(checkpoint.to_dict()), encoding="utf-8")
    os.replace(tmp, path)


# ── per-call ingest report ─────────────────────────────────────────────


@dataclass
class HeartbeatIngestReport:
    """Result of one :meth:`HeartbeatIngester.ingest_pending` invocation."""

    lines_scanned: int = 0
    notes_written: int = 0
    skipped_malformed: int = 0
    skipped_duplicate: int = 0
    new_offset: int = 0
    last_tick: int | None = None


# ── audit entry → Note projection ──────────────────────────────────────


def audit_entry_to_note(entry: dict[str, object]) -> Note | None:
    """Project one :class:`AuditEntry` dict into a T2 Episodic Note.

    Returns ``None`` when the entry is malformed and cannot be turned into
    a valid Note (caller should record this in the skipped_malformed
    counter; never raise from the ingest hot path).

    Routing:

    * ``world_state.last_active_workspace`` — drives ``project_slug`` and
      thus ``group_id = p:<slug>``.
    * When no workspace is active, the entry routes to the GLOBAL pool
      (``group_id = g:global``).

    Identity:

    * ``content_hash`` is the entry's ``idempotency_key`` (S-Auto Faz E
      already guarantees ``f"{tick}:{action}:{project_or_global}"``);
      re-ingesting the same line collapses to the same UUID5.
    """
    tick = entry.get("tick")
    if not isinstance(tick, int):
        return None
    trigger = entry.get("trigger", "")
    trigger_s = trigger if isinstance(trigger, str) else ""
    timestamp = entry.get("timestamp")
    when: datetime
    if isinstance(timestamp, str):
        try:
            when = datetime.fromisoformat(timestamp)
        except ValueError:
            when = datetime.now(UTC)
    else:
        when = datetime.now(UTC)
    world_state = entry.get("world_state", {})
    world_state_d = world_state if isinstance(world_state, dict) else {}
    workspace_raw = world_state_d.get("last_active_workspace")
    project_slug = workspace_raw if isinstance(workspace_raw, str) and workspace_raw else None

    decision_action = entry.get("decision_action")
    decision_action_s = decision_action if isinstance(decision_action, str) else "noop"
    result_outcome = entry.get("result_outcome")
    result_outcome_s = result_outcome if isinstance(result_outcome, str) else "n/a"
    air_alert = entry.get("air_alert")
    air_alert_s = air_alert if isinstance(air_alert, str) else None

    legal_actions_raw = entry.get("legal_actions")
    legal_actions = legal_actions_raw if isinstance(legal_actions_raw, list) else []

    # Compose the content body: short, structured, deterministic.
    summary_parts = [
        f"tick={tick}",
        f"trigger={trigger_s}",
        f"action={decision_action_s}",
        f"outcome={result_outcome_s}",
    ]
    if air_alert_s:
        summary_parts.append(f"AIR={air_alert_s}")
    if legal_actions:
        legal_str = ",".join(str(a) for a in legal_actions if isinstance(a, str))
        summary_parts.append(f"legal=[{legal_str}]")
    content = " | ".join(summary_parts)

    idempotency_key_raw = entry.get("idempotency_key")
    if isinstance(idempotency_key_raw, str) and idempotency_key_raw:
        content_hash = idempotency_key_raw
    else:
        content_hash = compute_content_hash(content)

    # GLOBAL pool routing when no project is active.
    if project_slug is None:
        group_id: str | None = GLOBAL_GROUP_ID
    else:
        group_id = derive_group_id(group_id=None, project_slug=project_slug)

    importance = 1.5 if air_alert_s else 1.0

    try:
        return Note(
            tier="episodic",
            kind="observation",
            content=content,
            intent=f"heartbeat tick {tick}",
            content_hash=content_hash,
            valid_from=when,
            project_slug=project_slug,
            group_id=group_id,
            session_id=f"heartbeat-tick-{tick}",
            source_pointer=f"heartbeat:{tick}",
            importance=importance,
        )
    except ValueError:
        return None


# ── ingester ───────────────────────────────────────────────────────────


@dataclass
class HeartbeatIngester:
    """Tail-follows ``~/.selffork/heartbeat/audit.jsonl`` and feeds T2.

    Construct one ingester per (project, store) pair. The store determines
    which pool receives the notes; pass the PROJECT pool's store for
    workspace-bound ticks and the GLOBAL pool's store for operator-level
    ticks. To split routing inside one ingester, give it
    :class:`~selffork_mind.store.pool.PoolResolver` and override
    :meth:`_resolve_store`.

    Wire:

        ingester = HeartbeatIngester(
            audit_path=default_audit_path(),
            store=duckdb_project_store,
            project_slug="selffork",
        )
        await ingester.ingest_pending()        # one-shot batch
        # OR
        task = asyncio.create_task(ingester.run())
        ...
        ingester.stop()
        await task
    """

    audit_path: Path
    store: MindStore
    project_slug: str | None = None
    checkpoint_path: Path | None = None
    poll_seconds: float = 1.0
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
    _ingest_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, init=False, repr=False,
    )

    def __post_init__(self) -> None:
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        if self.checkpoint_path is None:
            # Stem-prefixed so the audit log and its checkpoint stay paired
            # (multiple ingesters in one dir don't fight over the same file).
            self.checkpoint_path = (
                self.audit_path.parent / f"{self.audit_path.stem}.ingest-checkpoint.json"
            )

    # ── lifecycle ──────────────────────────────────────────────────────

    def stop(self) -> None:
        """Signal :meth:`run` to exit on its next iteration."""
        self._stop_event.set()

    async def run(self) -> None:
        """Tail-follow loop. Returns when :meth:`stop` is called."""
        self._stop_event.clear()
        while not self._stop_event.is_set():
            try:
                await self.ingest_pending()
            except Exception:
                _log.exception("heartbeat_ingest_loop_error path=%s", self.audit_path)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.poll_seconds,
                )
            except TimeoutError:
                continue

    async def ingest_pending(self) -> HeartbeatIngestReport:
        """Read new lines since the checkpoint and write T2 Notes.

        Serialised behind ``_ingest_lock`` so concurrent invocations
        (manual call while the ``run()`` loop is active, two daemons
        on the same audit file) cannot race on the checkpoint write or
        double-process the same lines (audit-god finding #2, ADR-009 §5).
        """
        async with self._ingest_lock:
            return await self._ingest_pending_locked()

    async def _ingest_pending_locked(self) -> HeartbeatIngestReport:
        report = HeartbeatIngestReport()
        assert self.checkpoint_path is not None  # noqa: S101 — populated by __post_init__
        checkpoint = await asyncio.to_thread(_load_checkpoint, self.checkpoint_path)
        report.new_offset = checkpoint.last_byte_offset
        report.last_tick = checkpoint.last_tick

        if not self.audit_path.is_file():
            return report

        # Read everything past the checkpoint in a single pass — the audit log
        # is append-only, so a streaming read is the cheapest correct option.
        def _read_new_lines() -> list[tuple[int, str]]:
            results: list[tuple[int, str]] = []
            with self.audit_path.open("rb") as fp:
                fp.seek(checkpoint.last_byte_offset)
                while True:
                    line_start = fp.tell()
                    raw = fp.readline()
                    if not raw:
                        break
                    try:
                        decoded = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        continue  # skip non-UTF8 noise
                    new_offset = fp.tell()
                    results.append((new_offset, decoded))
                    _ = line_start  # reserved for future per-line metrics
            return results

        new_lines = await asyncio.to_thread(_read_new_lines)
        if not new_lines:
            return report

        notes_to_write: list[Note] = []
        latest_offset = checkpoint.last_byte_offset
        latest_tick = checkpoint.last_tick

        for new_offset, raw in new_lines:
            report.lines_scanned += 1
            stripped = raw.strip()
            if not stripped:
                latest_offset = new_offset
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                report.skipped_malformed += 1
                latest_offset = new_offset
                continue
            if not isinstance(payload, dict):
                report.skipped_malformed += 1
                latest_offset = new_offset
                continue
            note = audit_entry_to_note(payload)
            if note is None:
                report.skipped_malformed += 1
                latest_offset = new_offset
                continue
            notes_to_write.append(note)
            latest_offset = new_offset
            tick_val = payload.get("tick")
            if isinstance(tick_val, int):
                latest_tick = tick_val

        if notes_to_write:
            written = await self.store.upsert_notes(notes_to_write)
            report.notes_written = len(written)

        new_checkpoint = IngestCheckpoint(
            last_byte_offset=latest_offset,
            last_tick=latest_tick,
            last_ingested_at=datetime.now(UTC),
        )
        await asyncio.to_thread(_save_checkpoint, self.checkpoint_path, new_checkpoint)
        report.new_offset = latest_offset
        report.last_tick = latest_tick
        return report

    # ── helpers (subclass hooks) ───────────────────────────────────────

    def iter_pending_entries(self) -> Iterator[dict[str, object]]:
        """Sync read-all helper for tests/diagnostics — never used in hot path."""
        if not self.audit_path.is_file():
            return
        with self.audit_path.open("r", encoding="utf-8") as fp:
            for raw in fp:
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    yield payload


def collect_entries(lines: Iterable[str]) -> list[dict[str, object]]:
    """Helper: parse a sequence of JSONL lines into entry dicts (for tests)."""
    out: list[dict[str, object]] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


# ── corrections.jsonl → T2 ingest (S-Bridge coaching loop) ─────────────


def correction_entry_to_note(entry: dict[str, object]) -> Note | None:
    """Project one :class:`Correction` JSONL row into a T2 Episodic Note.

    Returns ``None`` for malformed rows (caller bumps ``skipped_malformed``;
    we never raise from the ingest hot path).

    Identity:

    * ``content_hash = "correction:<idempotency_key>:<corrected_at>"`` —
      unique per write. The operator may correct the same audit entry
      twice with different reasoning; both rows MUST survive in T2 so
      S-Train sees the full coaching trajectory.

    Routing:

    * Corrections route to the GLOBAL pool by default (operator-level
      coaching is cross-project signal). A wrapping ingester can pass
      ``project_slug`` and route to that PROJECT pool instead — see
      :class:`CorrectionIngester`.

    Weighting:

    * ``importance=2.0`` (heartbeat observations are 1.0, AIR alerts 1.5).
      Operator corrections outrank routine ticks during retrieval and
      get high weight in the future S-Train fine-tune corpus.
    """
    key = entry.get("audit_idempotency_key")
    if not isinstance(key, str) or not key:
        return None
    text = entry.get("correction_text")
    if not isinstance(text, str) or not text.strip():
        return None
    suggested = entry.get("suggested_action")
    suggested_s = (
        suggested if isinstance(suggested, str) and suggested else None
    )
    source = entry.get("source")
    source_s = source if isinstance(source, str) and source else "operator"
    corrected_at_raw = entry.get("corrected_at")
    when: datetime
    if isinstance(corrected_at_raw, str):
        try:
            when = datetime.fromisoformat(corrected_at_raw)
        except ValueError:
            when = datetime.now(UTC)
    else:
        when = datetime.now(UTC)

    content_parts = [f"correction[{key}]", f"text={text}"]
    if suggested_s:
        content_parts.append(f"suggested={suggested_s}")
    content_parts.append(f"source={source_s}")
    content = " | ".join(content_parts)
    content_hash = f"correction:{key}:{when.isoformat()}"

    try:
        return Note(
            tier="episodic",
            kind="decision",
            content=content,
            intent=f"operator correction for {key}",
            content_hash=content_hash,
            valid_from=when,
            project_slug=None,
            group_id=GLOBAL_GROUP_ID,
            session_id=f"correction-{key}",
            source_pointer=f"correction:{key}",
            importance=2.0,
        )
    except ValueError:
        return None


@dataclass
class CorrectionIngester:
    """Tail-follows ``corrections.jsonl`` and feeds T2 as ``decision`` Notes.

    Mirrors :class:`HeartbeatIngester`'s lifecycle (run / stop /
    ingest_pending / checkpoint) but reads the sibling corrections file
    written by :meth:`AuditWriter.write_correction` (S-Vision Faz D +
    S-Bridge ``/correct`` Telegram command).

    Default routing is GLOBAL pool (operator coaching is cross-project
    signal). Pass ``project_slug`` to route into a PROJECT pool instead.

    Wire (typical):

        ingester = CorrectionIngester(
            corrections_path=default_corrections_path(),
            store=global_mind_store,
        )
        task = asyncio.create_task(ingester.run())
        ...
        ingester.stop()
        await task
    """

    corrections_path: Path
    store: MindStore
    project_slug: str | None = None
    checkpoint_path: Path | None = None
    poll_seconds: float = 1.0
    _stop_event: asyncio.Event = field(
        default_factory=asyncio.Event, init=False, repr=False,
    )
    _ingest_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, init=False, repr=False,
    )

    def __post_init__(self) -> None:
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        if self.checkpoint_path is None:
            self.checkpoint_path = (
                self.corrections_path.parent
                / f"{self.corrections_path.stem}.ingest-checkpoint.json"
            )

    def stop(self) -> None:
        """Signal :meth:`run` to exit on its next iteration."""
        self._stop_event.set()

    async def run(self) -> None:
        """Tail-follow loop. Returns when :meth:`stop` is called."""
        self._stop_event.clear()
        while not self._stop_event.is_set():
            try:
                await self.ingest_pending()
            except Exception:
                _log.exception(
                    "correction_ingest_loop_error path=%s",
                    self.corrections_path,
                )
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.poll_seconds,
                )
            except TimeoutError:
                continue

    async def ingest_pending(self) -> HeartbeatIngestReport:
        """Read new lines since the checkpoint and write T2 Notes."""
        async with self._ingest_lock:
            return await self._ingest_pending_locked()

    async def _ingest_pending_locked(self) -> HeartbeatIngestReport:
        report = HeartbeatIngestReport()
        assert self.checkpoint_path is not None  # noqa: S101
        checkpoint = await asyncio.to_thread(
            _load_checkpoint, self.checkpoint_path,
        )
        report.new_offset = checkpoint.last_byte_offset
        report.last_tick = checkpoint.last_tick

        if not self.corrections_path.is_file():
            return report

        def _read_new_lines() -> list[tuple[int, str]]:
            results: list[tuple[int, str]] = []
            with self.corrections_path.open("rb") as fp:
                fp.seek(checkpoint.last_byte_offset)
                while True:
                    raw = fp.readline()
                    if not raw:
                        break
                    try:
                        decoded = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    new_offset = fp.tell()
                    results.append((new_offset, decoded))
            return results

        new_lines = await asyncio.to_thread(_read_new_lines)
        if not new_lines:
            return report

        notes_to_write: list[Note] = []
        latest_offset = checkpoint.last_byte_offset
        latest_tick = checkpoint.last_tick

        for new_offset, raw in new_lines:
            report.lines_scanned += 1
            stripped = raw.strip()
            if not stripped:
                latest_offset = new_offset
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                report.skipped_malformed += 1
                latest_offset = new_offset
                continue
            if not isinstance(payload, dict):
                report.skipped_malformed += 1
                latest_offset = new_offset
                continue
            note = correction_entry_to_note(payload)
            if note is None:
                report.skipped_malformed += 1
                latest_offset = new_offset
                continue
            if self.project_slug is not None:
                note = Note(
                    tier=note.tier,
                    kind=note.kind,
                    content=note.content,
                    intent=note.intent,
                    content_hash=note.content_hash,
                    valid_from=note.valid_from,
                    project_slug=self.project_slug,
                    group_id=derive_group_id(
                        group_id=None,
                        project_slug=self.project_slug,
                    ),
                    session_id=note.session_id,
                    source_pointer=note.source_pointer,
                    importance=note.importance,
                )
            notes_to_write.append(note)
            latest_offset = new_offset

        if notes_to_write:
            written = await self.store.upsert_notes(notes_to_write)
            report.notes_written = len(written)

        new_checkpoint = IngestCheckpoint(
            last_byte_offset=latest_offset,
            last_tick=latest_tick,
            last_ingested_at=datetime.now(UTC),
        )
        await asyncio.to_thread(
            _save_checkpoint, self.checkpoint_path, new_checkpoint,
        )
        report.new_offset = latest_offset
        return report
