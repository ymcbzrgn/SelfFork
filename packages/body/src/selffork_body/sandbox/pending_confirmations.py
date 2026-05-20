"""Soft-confirm pending-action store (ADR-006 §4.5).

When ``DestructiveWhitelist.match`` returns a category, the action is
*paused* — the operator gets a Telegram message and has
``confirm_window_hours`` to explicitly approve. Silence past the window
auto-cancels the action (fail-safe NO).

This module models the queue + state machine. The Telegram outbound
wiring lives in the orchestrator (``selffork_orchestrator.telegram``),
plugged in via :attr:`PendingConfirmationStore.notify_hook` so this
module stays free of Telegram dependencies (Body pillar isolation).
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from .destructive_whitelist import CandidateAction, DestructiveCategory

PendingStatus = Literal["pending", "approved", "cancelled", "expired"]
NotifyOp = Literal["request", "approve", "cancel", "expire", "extend"]
NotifyHook = Callable[["PendingConfirmation", NotifyOp], None]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@dataclass
class PendingConfirmation:
    """A destructive action waiting for the operator's blessing."""

    id: str
    workspace_slug: str | None
    category_id: str
    category_description: str
    command_summary: str
    action_payload: dict
    asked_at: str
    expires_at: str
    status: PendingStatus = "pending"
    decided_at: str | None = None
    decided_by: str | None = None  # "operator", "expired", "self-jr-self-cancel"

    def time_left_seconds(self, now: datetime | None = None) -> int:
        now = now or _utc_now()
        ts = datetime.fromisoformat(self.expires_at)
        diff = (ts - now).total_seconds()
        return max(0, int(diff))

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.time_left_seconds(now) == 0 and self.status == "pending"


class PendingConfirmationStore:
    """Thread-safe in-memory store with optional JSONL persistence.

    The store is the source of truth for "what is Self Jr waiting on
    right now". The Dashboard banner, the Workspace banner, and the
    Telegram bot all read from this.

    Persistence: every mutation appends a line to
    ``audit_dir / "pending_confirmations.jsonl"`` so a restart can
    reconstruct the queue. ``load()`` replays the file at startup.
    """

    def __init__(
        self,
        *,
        audit_path: Path | None = None,
        notify_hook: NotifyHook | None = None,
    ) -> None:
        self._items: dict[str, PendingConfirmation] = {}
        self._lock = threading.RLock()
        self._audit_path = audit_path
        self._notify_hook = notify_hook
        # Byte offset into ``audit_path`` already replayed into
        # ``_items``. Used by :meth:`reload_from_disk` to skip work
        # that's already in memory (audit fix #14 — O(N) → O(Δ) per
        # poll). ``-1`` flags "not yet primed" so the first reload
        # walks the entire file even when nothing was written via
        # this instance.
        self._audit_file_offset = 0
        if audit_path is not None:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            if audit_path.is_file():
                self._load_from_disk()

    def set_notify_hook(self, hook: NotifyHook | None) -> None:
        """Late-bind the hook (e.g. once the Telegram bridge is ready)."""
        self._notify_hook = hook

    # ── public API ────────────────────────────────────────────────────

    def request(
        self,
        *,
        category: DestructiveCategory,
        action: CandidateAction,
        workspace_slug: str | None = None,
        command_summary: str | None = None,
    ) -> PendingConfirmation:
        """Open a new pending confirmation and return it.

        The caller (warden / orchestrator) then blocks the action until
        ``status`` flips to ``approved`` or the entry expires/cancels.
        """
        cid = uuid.uuid4().hex[:12]
        now = _utc_now()
        expires = now + timedelta(hours=category.confirm_window_hours)
        summary = command_summary or _summarize(action)
        entry = PendingConfirmation(
            id=cid,
            workspace_slug=workspace_slug,
            category_id=category.id,
            category_description=category.description,
            command_summary=summary,
            action_payload=_action_to_dict(action),
            asked_at=_iso(now),
            expires_at=_iso(expires),
            status="pending",
        )
        with self._lock:
            self._items[cid] = entry
            self._append_audit(entry, op="request")
        self._invoke_hook(entry, "request")
        return entry

    def approve(self, confirmation_id: str, *, by: str = "operator") -> PendingConfirmation | None:
        return self._decide(confirmation_id, status="approved", by=by)

    def cancel(self, confirmation_id: str, *, by: str = "operator") -> PendingConfirmation | None:
        return self._decide(confirmation_id, status="cancelled", by=by)

    def extend(
        self,
        confirmation_id: str,
        *,
        hours: int,
        by: str = "operator",
    ) -> PendingConfirmation | None:
        """Push out an entry's ``expires_at`` by ``hours``.

        ADR-006 §10.1 ``/extend`` mitigation: an operator who needs more
        time before a destructive action can extend the window from
        Telegram (``/extend 8h``) or the workspace banner. Audit retains
        the new expiry via the ``extend`` row; ``decided_by`` carries
        the request origin while ``status`` stays ``"pending"``.
        """
        if hours <= 0:
            return self.get(confirmation_id)
        with self._lock:
            entry = self._items.get(confirmation_id)
            if entry is None or entry.status != "pending":
                return entry
            current = datetime.fromisoformat(entry.expires_at)
            entry.expires_at = _iso(current + timedelta(hours=hours))
            entry.decided_by = f"extend:{by}"  # diagnostic; status stays pending
            self._append_audit(entry, op="extend")
        self._invoke_hook(entry, "extend")
        return entry

    def expire_stale(self, now: datetime | None = None) -> list[PendingConfirmation]:
        """Sweep expired entries and mark them ``expired``.

        Returns the list that flipped — callers can hand these to the
        Telegram bridge for a "cancelled (silence)" notification. The
        configured :attr:`notify_hook` is invoked once per flipped
        entry with ``op="expire"`` for symmetry with the other ops.
        """
        now = now or _utc_now()
        flipped: list[PendingConfirmation] = []
        with self._lock:
            for entry in self._items.values():
                if entry.is_expired(now=now):
                    entry.status = "expired"
                    entry.decided_at = _iso(now)
                    entry.decided_by = "expired"
                    flipped.append(entry)
                    self._append_audit(entry, op="expire")
        for entry in flipped:
            self._invoke_hook(entry, "expire")
        return flipped

    def get(self, confirmation_id: str) -> PendingConfirmation | None:
        with self._lock:
            return self._items.get(confirmation_id)

    def list_pending(
        self, *, workspace_slug: str | None = None
    ) -> list[PendingConfirmation]:
        """All pending entries; optionally filtered by workspace."""
        now = _utc_now()
        with self._lock:
            out: list[PendingConfirmation] = []
            for entry in self._items.values():
                if entry.status != "pending":
                    continue
                if entry.is_expired(now=now):
                    continue
                if workspace_slug is not None and entry.workspace_slug != workspace_slug:
                    continue
                out.append(entry)
            out.sort(key=lambda e: e.asked_at)
            return out

    def all(self) -> list[PendingConfirmation]:
        with self._lock:
            return list(self._items.values())

    def reload_from_disk(self) -> None:
        """Replay newly-appended audit lines into the in-memory dict.

        Cross-process consistency hook: ``selffork run`` (the producer
        of destructive requests) and ``selffork ui`` (this consumer)
        share the JSONL file but each owns its own in-memory dict.
        Dashboard read handlers call this before listing so a request
        opened in the run process becomes visible in the UI without
        restart.

        Audit fix #14: this method used to clear ``_items`` and replay
        the entire file on every call — O(N) per topbar poll. The
        JSONL log is append-only, so we now stash a byte offset and
        only parse lines that landed since the previous reload. If the
        file shrinks (rotation / truncation) we full-reset and walk
        from the start to stay consistent.
        """
        if self._audit_path is None or not self._audit_path.is_file():
            return
        with self._lock:
            try:
                size = self._audit_path.stat().st_size
            except OSError:
                return
            if size < self._audit_file_offset:
                # The file was rotated or truncated under us — drop the
                # in-memory snapshot and walk again from byte zero.
                self._items.clear()
                self._audit_file_offset = 0
            if size == self._audit_file_offset:
                return  # nothing new since the last replay
            self._replay_from_offset()

    def _replay_from_offset(self) -> None:
        """Parse audit lines starting at ``_audit_file_offset``.

        Caller holds ``self._lock``. Each successful line advances the
        offset; corrupted lines log-and-skip but the offset still moves
        forward so the loop doesn't spin on bad input.
        """
        if self._audit_path is None:
            return
        with self._audit_path.open("r", encoding="utf-8") as f:
            f.seek(self._audit_file_offset)
            for line in f:
                stripped = line.strip()
                if stripped:
                    try:
                        record = json.loads(stripped)
                        raw = record["entry"]
                        entry = PendingConfirmation(**raw)
                        self._items[entry.id] = entry
                    except (json.JSONDecodeError, TypeError, KeyError):
                        continue
            self._audit_file_offset = f.tell()

    # ── internals ─────────────────────────────────────────────────────

    def _decide(
        self,
        confirmation_id: str,
        *,
        status: PendingStatus,
        by: str,
    ) -> PendingConfirmation | None:
        with self._lock:
            entry = self._items.get(confirmation_id)
            if entry is None or entry.status != "pending":
                return entry
            entry.status = status
            entry.decided_at = _iso(_utc_now())
            entry.decided_by = by
            self._append_audit(entry, op="decide")
            op: NotifyOp = "approve" if status == "approved" else "cancel"
        # Hook fires outside the lock — a slow Telegram round-trip
        # must not stall concurrent approve/cancel callers.
        self._invoke_hook(entry, op)
        return entry

    def _invoke_hook(self, entry: PendingConfirmation, op: NotifyOp) -> None:
        """Best-effort hook fan-out. Hook failure MUST NOT break the store.

        The hook signature is sync; outbound senders (Telegram) wrap any
        async work in their own ``asyncio.create_task`` so this helper
        stays trivial to call from any thread.
        """
        hook = self._notify_hook
        if hook is None:
            return
        try:
            hook(entry, op)
        except Exception:
            # Telegram outages, allowlist mistakes, and serialization
            # bugs must never crash the destructive guard. The store
            # remains the source of truth; the hook is a side-effect.
            return

    def _append_audit(self, entry: PendingConfirmation, *, op: str) -> None:
        if self._audit_path is None:
            return
        record = {"op": op, "entry": asdict(entry)}
        try:
            with self._audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            # Best-effort persistence — failure to audit must NOT block
            # the in-memory queue (the alternative is silent action
            # leakage which is the worst possible outcome here).
            pass

    def _load_from_disk(self) -> None:
        """Constructor-time replay; identical to the incremental path
        but starts at offset 0 and primes :attr:`_audit_file_offset`."""
        if self._audit_path is None or not self._audit_path.is_file():
            return
        self._audit_file_offset = 0
        with self._lock:
            self._replay_from_offset()


def _summarize(action: CandidateAction) -> str:
    """Short, single-line description for UI + Telegram preview."""
    if action.tool:
        args = " ".join(action.args)
        return f"{action.tool} {args}".strip()
    if action.sql:
        snippet = action.sql.strip().splitlines()[0][:80]
        return snippet
    if action.url:
        return f"{action.http_method or 'GET'} {action.url}"
    return "(unknown action)"


def _action_to_dict(action: CandidateAction) -> dict:
    return {
        "tool": action.tool,
        "args": list(action.args),
        "env": dict(action.env),
        "sql": action.sql,
        "url": action.url,
        "http_method": action.http_method,
    }


__all__ = [
    "NotifyHook",
    "NotifyOp",
    "PendingConfirmation",
    "PendingConfirmationStore",
    "PendingStatus",
]


# Re-export iterable helpers for type-hint consumers.
PendingIterable = Iterable[PendingConfirmation]
