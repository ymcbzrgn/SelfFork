"""Interactive structured-tool round-trip (S-Bridge CORE).

Self Jr can emit ``AskUserQuestion``-style structured choice prompts as
``<selffork-tool-call>`` blocks (see :mod:`cli_agent.structured_tools`).
Before S-Bridge those calls hit an unregistered tool and silently
errored; this module ships the **interactive bridge**:

1. The tool registers a :class:`PendingStructuredQuestion` (correlation
   id + payload + asyncio.Event).
2. The handler ``await``s on the event with a configurable timeout
   (default 1h, override
   ``SELFFORK_STRUCTURED_QUESTION_TIMEOUT_SECONDS``).
3. The operator answers via Telegram ``/answer <correlation_id>
   <text>`` (S-Bridge Telegram inbound — see
   :mod:`telegram.inbound_router`) or the Talk UI POSTs to the
   structured-answer API (S-Bridge UI follow-up).
4. The event fires, the handler returns
   ``{"status": "answered", "correlation_id": ..., "answer": ...}`` as a
   :class:`~selffork_orchestrator.tools.base.ToolResult` payload, and
   Self Jr's next round sees the answer spliced into chat history.

Timeout returns ``{"status": "timeout", ...}``; Self Jr decides what
to do (retry / proceed without input / surface to operator).

Design choices:

* **In-memory store**, no disk persistence — a pending question is
  scoped to one ``Session._run_agent`` lifetime and dies with the
  process. Future S-Train can lift this to disk if a long-running
  workspace warrants it.
* **asyncio.Event** rather than polling — wake-up latency is bounded by
  the producer's event-loop tick, not by a sleep interval.
* **Pydantic v2 schemas** mirror Anthropic's ``AskUserQuestion`` shape
  so Self Jr's emits stay portable; ``extra="ignore"`` tolerates
  future field additions without crashing the handler.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

import anyio
from pydantic import BaseModel, ConfigDict, Field

from selffork_orchestrator.tools.base import (
    ToolContext,
    ToolSpec,
)

__all__ = [
    "DEFAULT_CLEANUP_INTERVAL_SECONDS",
    "DEFAULT_SQLITE_POLL_INTERVAL_SECONDS",
    "DEFAULT_STRUCTURED_QUESTION_TIMEOUT_SECONDS",
    "AskUserOption",
    "AskUserQuestion",
    "AskUserQuestionArgs",
    "PendingStructuredQuestion",
    "PendingStructuredQuestionStore",
    "SqlitePendingStructuredQuestionStore",
    "build_ask_user_question_spec",
    "build_structured_question_store",
    "cleanup_loop",
    "handle_ask_user_question",
]


_log = logging.getLogger(__name__)


DEFAULT_STRUCTURED_QUESTION_TIMEOUT_SECONDS: float = 3600.0
"""Default operator-answer timeout (one hour).

Override via ``SELFFORK_STRUCTURED_QUESTION_TIMEOUT_SECONDS``. Floor
clamp at 5 seconds — anything lower defeats the round-trip purpose
and is almost certainly a misconfiguration."""


# ── pending question record ─────────────────────────────────────────


@dataclass(slots=True)
class PendingStructuredQuestion:
    """One in-flight AskUserQuestion awaiting an operator answer.

    ``event`` is asyncio-based: the producer (tool handler) awaits it,
    the consumer (Telegram ``/answer`` / Talk UI POST) sets it after
    writing ``answer`` and ``answered_at``.
    """

    correlation_id: str
    payload: dict[str, Any]
    session_id: str | None
    created_at: datetime
    expires_at: datetime
    event: asyncio.Event
    answer: str | None = None
    answered_at: datetime | None = None
    cancelled: bool = False


# ── store (process-local, asyncio-coordinated) ──────────────────────


class PendingStructuredQuestionStore:
    """In-memory registry of pending structured questions.

    One instance per orchestrator process. Both the producer side
    (``await register/wait_for_answer``) and the consumer side
    (``submit_answer/cancel`` from Telegram or REST) hit the same
    instance; the asyncio.Event in each entry handshakes them.

    Thread-safety: an internal ``asyncio.Lock`` serialises mutations
    so concurrent register/submit/cancel calls keep the dict and
    event in lockstep. Read paths (:meth:`get`, :meth:`list_pending`)
    are deliberately lock-free — they tolerate slightly stale snapshots
    so a slow consumer can poll without blocking producers.
    """

    def __init__(self) -> None:
        self._entries: dict[str, PendingStructuredQuestion] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        *,
        payload: dict[str, Any],
        session_id: str | None = None,
        ttl_seconds: float = DEFAULT_STRUCTURED_QUESTION_TIMEOUT_SECONDS,
    ) -> PendingStructuredQuestion:
        """Create a new pending entry and return it.

        The returned entry's ``correlation_id`` is the canonical handle
        the operator references when answering. ``ttl_seconds`` controls
        the wall-clock expiry stamp (the asyncio wait timeout is
        separate, see :meth:`wait_for_answer`).
        """
        async with self._lock:
            corr_id = uuid.uuid4().hex[:8]
            now = datetime.now(UTC)
            entry = PendingStructuredQuestion(
                correlation_id=corr_id,
                payload=payload,
                session_id=session_id,
                created_at=now,
                expires_at=now + timedelta(seconds=max(5.0, ttl_seconds)),
                event=asyncio.Event(),
            )
            self._entries[corr_id] = entry
            _log.info(
                "structured_question_registered",
                extra={
                    "correlation_id": corr_id,
                    "session_id": session_id,
                    "ttl_seconds": ttl_seconds,
                },
            )
            return entry

    async def submit_answer(
        self, correlation_id: str, answer: str,
    ) -> bool:
        """Record the operator's answer and wake the waiting tool.

        Returns ``True`` on success, ``False`` when no matching entry
        exists or the entry is already resolved (answered / cancelled
        / timed-out). Idempotent — a second submit on the same entry
        is a no-op.
        """
        async with self._lock:
            entry = self._entries.get(correlation_id)
            if entry is None or entry.event.is_set():
                return False
            entry.answer = answer
            entry.answered_at = datetime.now(UTC)
            entry.event.set()
            _log.info(
                "structured_question_answered",
                extra={
                    "correlation_id": correlation_id,
                    "session_id": entry.session_id,
                },
            )
            return True

    async def cancel(self, correlation_id: str) -> bool:
        """Cancel a pending entry — wakes the waiter with no answer."""
        async with self._lock:
            entry = self._entries.get(correlation_id)
            if entry is None or entry.event.is_set():
                return False
            entry.cancelled = True
            entry.event.set()
            _log.info(
                "structured_question_cancelled",
                extra={"correlation_id": correlation_id},
            )
            return True

    async def wait_for_answer(
        self, correlation_id: str, *, timeout_seconds: float,
    ) -> str | None:
        """Await an answer up to ``timeout_seconds``.

        Returns the answer string on success, ``None`` on timeout /
        cancellation / missing entry. The caller distinguishes by
        inspecting :meth:`get` after the wait.
        """
        entry = self._entries.get(correlation_id)
        if entry is None:
            return None
        try:
            await asyncio.wait_for(
                entry.event.wait(), timeout=timeout_seconds,
            )
        except TimeoutError:
            return None
        if entry.cancelled:
            return None
        return entry.answer

    async def get(
        self, correlation_id: str,
    ) -> PendingStructuredQuestion | None:
        """Read one entry — does NOT remove it from the store.

        Async (Faz 0 F2) so the in-memory and SQLite stores share one
        contract — callers can ``await store.get(...)`` regardless of
        backend. The in-memory implementation is still a constant-time
        dict access; the ``async`` is for shape consistency only.
        """
        return self._entries.get(correlation_id)

    async def list_pending(self) -> list[PendingStructuredQuestion]:
        """Snapshot of every unanswered entry, oldest first."""
        return sorted(
            (e for e in self._entries.values() if not e.event.is_set()),
            key=lambda e: e.created_at,
        )

    async def cleanup_expired(self) -> int:
        """Drop entries past ``expires_at``. Returns the count removed.

        Sets the event on each so any still-waiting tool exits its
        ``wait_for_answer`` cleanly with ``None``. Safe to call
        periodically; the store also tolerates not being cleaned (it
        just grows).
        """
        async with self._lock:
            now = datetime.now(UTC)
            expired_ids = [
                cid
                for cid, entry in self._entries.items()
                if entry.expires_at < now
            ]
            for cid in expired_ids:
                entry = self._entries[cid]
                if not entry.event.is_set():
                    entry.cancelled = True
                    entry.event.set()
                del self._entries[cid]
            if expired_ids:
                _log.info(
                    "structured_question_cleanup",
                    extra={"removed": len(expired_ids)},
                )
            return len(expired_ids)


DEFAULT_CLEANUP_INTERVAL_SECONDS: float = 60.0


async def cleanup_loop(
    store: PendingStructuredQuestionStore
    | SqlitePendingStructuredQuestionStore,
    interval_seconds: float = DEFAULT_CLEANUP_INTERVAL_SECONDS,
) -> None:
    """Periodically purge expired entries from ``store``.

    Mirrors :func:`selffork_orchestrator.telegram.expire_loop.expire_loop`:
    sweep first, then sleep, with a final sweep on cancellation. Dashboard
    lifespan owns this loop so a long-lived process doesn't accumulate
    stale pending dict entries (Faz 0 substrate fix — ``cleanup_expired``
    had no production caller pre-fix). Transient store failures log and
    continue so a one-off bug cannot kill the watchdog. Accepts either
    the in-memory or SQLite-backed store (Faz 0 F2).
    """
    if interval_seconds <= 0:
        msg = "interval_seconds must be positive"
        raise ValueError(msg)
    try:
        while True:
            try:
                await store.cleanup_expired()
            except Exception:  # pragma: no cover — defensive log only
                _log.exception("structured_question_cleanup_loop_failed")
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            await store.cleanup_expired()
        raise


# ── SQLite-backed store (cross-process variant) ─────────────────────


DEFAULT_SQLITE_POLL_INTERVAL_SECONDS: float = 0.5
"""How often :class:`SqlitePendingStructuredQuestionStore` re-checks the
database for an answer while a producer is blocked. 0.5s is fast enough
for round-loop responsiveness without thrashing the disk; humans rarely
answer in under a second anyway."""


_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS pending_structured_questions (
    correlation_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    session_id TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    answer TEXT,
    answered_at TEXT,
    cancelled INTEGER NOT NULL DEFAULT 0
);
"""

_SQLITE_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_psq_expires_at "
    "ON pending_structured_questions(expires_at);"
)


class SqlitePendingStructuredQuestionStore:
    """Cross-process structured-question store backed by SQLite.

    Same async API as :class:`PendingStructuredQuestionStore`. The
    operational difference: the in-memory store handshakes producer +
    consumer via an ``asyncio.Event`` that only crosses **inside one
    process**. ``selffork run`` runs the round-loop in a subprocess but
    the dashboard process owns Telegram ``/answer`` — without a shared
    backing store the subprocess never sees the answer (silent
    timeout). This class writes every pending entry to a SQLite file
    (default ``~/.selffork/structured_questions.db``) that both
    processes open; ``wait_for_answer`` polls the row instead of
    blocking on an event.

    Threading: SQLite calls run inside ``anyio.to_thread.run_sync`` so
    the dashboard's event loop never blocks on disk I/O. WAL keeps
    reads non-blocking against the rare write; ``busy_timeout`` waits
    out brief contention between the two processes.
    """

    def __init__(
        self,
        *,
        db_path: Path,
        poll_interval_seconds: float = DEFAULT_SQLITE_POLL_INTERVAL_SECONDS,
        busy_timeout_ms: int = 5000,
    ) -> None:
        if poll_interval_seconds <= 0:
            msg = "poll_interval_seconds must be positive"
            raise ValueError(msg)
        self._db_path = db_path
        self._poll_interval = poll_interval_seconds
        self._busy_timeout_ms = busy_timeout_ms
        self._setup_done = False
        self._setup_lock = asyncio.Lock()

    async def _ensure_setup(self) -> None:
        # Single-check under the lock — setup runs once and is short,
        # so the lock cost dominates only on cold start.
        async with self._setup_lock:
            if self._setup_done:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            await anyio.to_thread.run_sync(self._init_schema_sync)
            self._setup_done = True

    def _init_schema_sync(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(_SQLITE_DDL)
            conn.execute(_SQLITE_INDEX_DDL)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False, timeout=2.0,
        )
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms};")
        return conn

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> PendingStructuredQuestion:
        created_at = datetime.fromisoformat(row["created_at"])
        expires_at = datetime.fromisoformat(row["expires_at"])
        answered_at = (
            datetime.fromisoformat(row["answered_at"])
            if row["answered_at"] else None
        )
        entry = PendingStructuredQuestion(
            correlation_id=row["correlation_id"],
            payload=json.loads(row["payload_json"]),
            session_id=row["session_id"],
            created_at=created_at,
            expires_at=expires_at,
            event=asyncio.Event(),  # vestigial — wait_for_answer polls
            answer=row["answer"],
            answered_at=answered_at,
            cancelled=bool(row["cancelled"]),
        )
        # Mirror in-memory semantics: a resolved row presents an
        # already-set event so ``list_pending`` excludes it.
        if entry.answer is not None or entry.cancelled:
            entry.event.set()
        return entry

    async def register(
        self,
        *,
        payload: dict[str, Any],
        session_id: str | None = None,
        ttl_seconds: float = DEFAULT_STRUCTURED_QUESTION_TIMEOUT_SECONDS,
    ) -> PendingStructuredQuestion:
        await self._ensure_setup()
        corr_id = uuid.uuid4().hex[:8]
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=max(5.0, ttl_seconds))
        entry = PendingStructuredQuestion(
            correlation_id=corr_id,
            payload=payload,
            session_id=session_id,
            created_at=now,
            expires_at=expires_at,
            event=asyncio.Event(),
        )

        def _insert() -> None:
            with closing(self._connect()) as conn:
                conn.execute(
                    "INSERT INTO pending_structured_questions "
                    "(correlation_id, payload_json, session_id, "
                    "created_at, expires_at, answer, answered_at, "
                    "cancelled) VALUES (?, ?, ?, ?, ?, NULL, NULL, 0)",
                    (
                        corr_id,
                        json.dumps(payload),
                        session_id,
                        now.isoformat(),
                        expires_at.isoformat(),
                    ),
                )
                conn.commit()

        await anyio.to_thread.run_sync(_insert)
        _log.info(
            "structured_question_registered",
            extra={
                "correlation_id": corr_id,
                "session_id": session_id,
                "ttl_seconds": ttl_seconds,
                "backend": "sqlite",
            },
        )
        return entry

    async def submit_answer(
        self, correlation_id: str, answer: str,
    ) -> bool:
        await self._ensure_setup()
        answered_at = datetime.now(UTC).isoformat()

        def _update() -> int:
            with closing(self._connect()) as conn:
                cur = conn.execute(
                    "UPDATE pending_structured_questions "
                    "SET answer = ?, answered_at = ? "
                    "WHERE correlation_id = ? "
                    "  AND answer IS NULL "
                    "  AND cancelled = 0",
                    (answer, answered_at, correlation_id),
                )
                conn.commit()
                return cur.rowcount

        rowcount = await anyio.to_thread.run_sync(_update)
        if rowcount > 0:
            _log.info(
                "structured_question_answered",
                extra={
                    "correlation_id": correlation_id,
                    "backend": "sqlite",
                },
            )
            return True
        return False

    async def cancel(self, correlation_id: str) -> bool:
        await self._ensure_setup()

        def _update() -> int:
            with closing(self._connect()) as conn:
                cur = conn.execute(
                    "UPDATE pending_structured_questions "
                    "SET cancelled = 1 "
                    "WHERE correlation_id = ? "
                    "  AND answer IS NULL "
                    "  AND cancelled = 0",
                    (correlation_id,),
                )
                conn.commit()
                return cur.rowcount

        rowcount = await anyio.to_thread.run_sync(_update)
        if rowcount > 0:
            _log.info(
                "structured_question_cancelled",
                extra={
                    "correlation_id": correlation_id,
                    "backend": "sqlite",
                },
            )
            return True
        return False

    async def wait_for_answer(
        self, correlation_id: str, *, timeout_seconds: float,
    ) -> str | None:
        """Poll the row until an answer / cancellation / timeout."""
        await self._ensure_setup()
        deadline = asyncio.get_event_loop().time() + max(0.0, timeout_seconds)
        while True:
            entry = await self.get(correlation_id)
            if entry is None:
                return None
            if entry.answer is not None:
                return entry.answer
            if entry.cancelled:
                return None
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(self._poll_interval, remaining))

    async def get(
        self, correlation_id: str,
    ) -> PendingStructuredQuestion | None:
        await self._ensure_setup()

        def _select() -> sqlite3.Row | None:
            with closing(self._connect()) as conn:
                conn.row_factory = sqlite3.Row
                row: sqlite3.Row | None = conn.execute(
                    "SELECT * FROM pending_structured_questions "
                    "WHERE correlation_id = ?",
                    (correlation_id,),
                ).fetchone()
                return row

        row = await anyio.to_thread.run_sync(_select)
        if row is None:
            return None
        return self._row_to_entry(row)

    async def list_pending(self) -> list[PendingStructuredQuestion]:
        await self._ensure_setup()

        def _select() -> list[sqlite3.Row]:
            with closing(self._connect()) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM pending_structured_questions "
                    "WHERE answer IS NULL AND cancelled = 0 "
                    "ORDER BY created_at ASC",
                ).fetchall()
                return list(rows)

        rows = await anyio.to_thread.run_sync(_select)
        return [self._row_to_entry(r) for r in rows]

    async def cleanup_expired(self) -> int:
        await self._ensure_setup()
        now_iso = datetime.now(UTC).isoformat()

        def _delete() -> int:
            with closing(self._connect()) as conn:
                cur = conn.execute(
                    "DELETE FROM pending_structured_questions "
                    "WHERE expires_at < ? "
                    "  AND answer IS NULL "
                    "  AND cancelled = 0",
                    (now_iso,),
                )
                conn.commit()
                return cur.rowcount

        removed = await anyio.to_thread.run_sync(_delete)
        if removed:
            _log.info(
                "structured_question_cleanup",
                extra={"removed": removed, "backend": "sqlite"},
            )
        return removed


def _resolve_store_path_from_env() -> Path | None:
    """Env-knob lookup for the SQLite path. ``None`` ⇒ in-memory."""
    raw = os.environ.get("SELFFORK_STRUCTURED_QUESTION_DB", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def build_structured_question_store(
    *,
    db_path: Path | None = None,
) -> PendingStructuredQuestionStore | SqlitePendingStructuredQuestionStore:
    """Factory — disk-backed when a path is supplied, in-memory otherwise.

    ``db_path`` precedence: explicit argument > ``SELFFORK_STRUCTURED_QUESTION_DB``
    env > ``None`` (in-memory). The in-memory store remains the default for
    tests and orphan boots; the SQLite store is opt-in via env or explicit
    construction so existing callers (the legacy ``selffork run`` subprocess
    + dashboard pair) keep working until both wire the shared path.
    """
    resolved = db_path if db_path is not None else _resolve_store_path_from_env()
    if resolved is None:
        return PendingStructuredQuestionStore()
    return SqlitePendingStructuredQuestionStore(db_path=resolved)


# ── AskUserQuestion args schema (mirrors Anthropic's tool format) ───


class AskUserOption(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(min_length=0, max_length=2000)] = ""


class AskUserQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: Annotated[str, Field(min_length=1, max_length=4000)]
    header: Annotated[str, Field(min_length=1, max_length=80)]
    options: Annotated[list[AskUserOption], Field(min_length=2, max_length=4)]
    multiSelect: bool = False  # noqa: N815 — wire-format parity with Anthropic AskUserQuestion


class AskUserQuestionArgs(BaseModel):
    """AskUserQuestion-style structured prompt.

    Self Jr emits one or more questions; the handler surfaces them to
    the operator and blocks until an answer arrives (or the timeout
    fires). The schema mirrors Anthropic's tool exactly so Self Jr's
    fine-tune corpus stays portable.
    """

    model_config = ConfigDict(extra="ignore")

    questions: Annotated[
        list[AskUserQuestion], Field(min_length=1, max_length=4),
    ]


# ── tool handler + spec ─────────────────────────────────────────────


def _resolve_timeout_seconds() -> float:
    """Read ``SELFFORK_STRUCTURED_QUESTION_TIMEOUT_SECONDS`` with safe floor."""
    raw = os.environ.get(
        "SELFFORK_STRUCTURED_QUESTION_TIMEOUT_SECONDS", "",
    ).strip()
    if not raw:
        return DEFAULT_STRUCTURED_QUESTION_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_STRUCTURED_QUESTION_TIMEOUT_SECONDS
    return max(5.0, value)


async def handle_ask_user_question(
    ctx: ToolContext, args: AskUserQuestionArgs,
) -> dict[str, Any]:
    """Register a pending question, surface it, await operator answer.

    ToolResult payload contract:

    * ``status="unwired"`` — no pending store on the context. Self Jr
      should fall back to non-interactive behaviour.
    * ``status="answered"`` — operator answered;
      ``answer`` is their reply (raw string — option label or freeform
      depending on the Telegram / UI side that posted it).
    * ``status="timeout"`` — no answer within the timeout. Self Jr
      decides whether to retry, proceed, or surface to operator.
    * ``status="cancelled"`` — operator explicitly cancelled the
      pending question (e.g. ``/cancel`` Telegram command).

    All branches include ``correlation_id`` for cross-referencing with
    the activity feed + Telegram ``/answer`` flow.
    """
    store = ctx.structured_question_store
    if not isinstance(
        store,
        (PendingStructuredQuestionStore, SqlitePendingStructuredQuestionStore),
    ):
        return {
            "status": "unwired",
            "correlation_id": None,
            "answer": None,
            "message": (
                "PendingStructuredQuestionStore is not wired into this "
                "session. The orchestrator must inject it (in-memory or "
                "SQLite-backed) via ToolContext for AskUserQuestion to "
                "function."
            ),
        }

    timeout_seconds = _resolve_timeout_seconds()
    payload = args.model_dump()
    entry = await store.register(
        payload=payload,
        session_id=ctx.session_id,
        ttl_seconds=timeout_seconds + 60,
    )

    audit_logger = ctx.audit_logger
    if audit_logger is not None and hasattr(audit_logger, "emit"):
        # Best-effort observability: surface the correlation id to the
        # dashboard activity feed via an existing audit category so
        # operators can copy it for ``/answer``. Failures don't break
        # the tool — auditing is observability, not correctness.
        try:
            audit_logger.emit(
                category="tool.structured_question",
                payload={
                    "correlation_id": entry.correlation_id,
                    "session_id": entry.session_id,
                    "questions": payload.get("questions", []),
                    "timeout_seconds": timeout_seconds,
                    "pending": True,
                },
            )
        except Exception:
            _log.warning(
                "structured_question_audit_failed",
                exc_info=True,
                extra={"correlation_id": entry.correlation_id},
            )

    answer = await store.wait_for_answer(
        entry.correlation_id, timeout_seconds=timeout_seconds,
    )

    if answer is not None:
        return {
            "status": "answered",
            "correlation_id": entry.correlation_id,
            "answer": answer,
        }
    # Re-read the entry to distinguish cancellation vs timeout.
    final = await store.get(entry.correlation_id)
    if final is not None and final.cancelled:
        return {
            "status": "cancelled",
            "correlation_id": entry.correlation_id,
            "answer": None,
            "message": "Operator cancelled the pending question.",
        }
    return {
        "status": "timeout",
        "correlation_id": entry.correlation_id,
        "answer": None,
        "message": (
            f"Operator did not answer within {timeout_seconds:.0f}s. "
            "Re-emit the question or proceed without input."
        ),
    }


def build_ask_user_question_spec() -> ToolSpec[AskUserQuestionArgs]:
    """Construct the ``AskUserQuestion`` :class:`ToolSpec` for registry use."""
    return ToolSpec(
        name="AskUserQuestion",
        description=(
            "Ask the operator a structured choice question and BLOCK "
            "the round-loop until they answer via Telegram /answer or "
            "the Talk UI. Times out at "
            f"SELFFORK_STRUCTURED_QUESTION_TIMEOUT_SECONDS "
            f"(default {DEFAULT_STRUCTURED_QUESTION_TIMEOUT_SECONDS:.0f}s)."
        ),
        args_model=AskUserQuestionArgs,
        handler=handle_ask_user_question,
    )
