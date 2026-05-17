"""Soft-confirm pending-action store (ADR-006 §4.5).

When ``DestructiveWhitelist.match`` returns a category, the action is
*paused* — the operator gets a Telegram message and has
``confirm_window_hours`` to explicitly approve. Silence past the window
auto-cancels the action (fail-safe NO).

This module models the queue + state machine. Wiring up the Telegram
outbound and the warden interception happens in ``warden.py`` and the
Telegram bridge (Task #9).
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Literal

from .destructive_whitelist import CandidateAction, DestructiveCategory

PendingStatus = Literal["pending", "approved", "cancelled", "expired"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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

    def __init__(self, *, audit_path: Path | None = None) -> None:
        self._items: dict[str, PendingConfirmation] = {}
        self._lock = threading.RLock()
        self._audit_path = audit_path
        if audit_path is not None:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            if audit_path.is_file():
                self._load_from_disk()

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
        return entry

    def approve(self, confirmation_id: str, *, by: str = "operator") -> PendingConfirmation | None:
        return self._decide(confirmation_id, status="approved", by=by)

    def cancel(self, confirmation_id: str, *, by: str = "operator") -> PendingConfirmation | None:
        return self._decide(confirmation_id, status="cancelled", by=by)

    def expire_stale(self, now: datetime | None = None) -> list[PendingConfirmation]:
        """Sweep expired entries and mark them ``expired``.

        Returns the list that flipped — callers can hand these to the
        Telegram bridge for a "cancelled (silence)" notification.
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
            return entry

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
        if self._audit_path is None or not self._audit_path.is_file():
            return
        with self._audit_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    raw = record["entry"]
                    entry = PendingConfirmation(**raw)
                    self._items[entry.id] = entry
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue


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
    "PendingConfirmation",
    "PendingConfirmationStore",
    "PendingStatus",
]


# Re-export iterable helpers for type-hint consumers.
PendingIterable = Iterable[PendingConfirmation]
