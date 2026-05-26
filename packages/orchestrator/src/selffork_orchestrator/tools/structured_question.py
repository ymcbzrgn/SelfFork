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
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from selffork_orchestrator.tools.base import (
    ToolContext,
    ToolSpec,
)

__all__ = [
    "DEFAULT_STRUCTURED_QUESTION_TIMEOUT_SECONDS",
    "AskUserOption",
    "AskUserQuestion",
    "AskUserQuestionArgs",
    "PendingStructuredQuestion",
    "PendingStructuredQuestionStore",
    "build_ask_user_question_spec",
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

    def get(
        self, correlation_id: str,
    ) -> PendingStructuredQuestion | None:
        """Read one entry — does NOT remove it from the store."""
        return self._entries.get(correlation_id)

    def list_pending(self) -> list[PendingStructuredQuestion]:
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
    if not isinstance(store, PendingStructuredQuestionStore):
        return {
            "status": "unwired",
            "correlation_id": None,
            "answer": None,
            "message": (
                "PendingStructuredQuestionStore is not wired into this "
                "session. The orchestrator must inject it via "
                "ToolContext for AskUserQuestion to function."
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
    final = store.get(entry.correlation_id)
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
