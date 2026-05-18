"""FastAPI router for the Talk surface — operator ↔ Self Jr — S1.

Endpoints:

* ``GET  /api/talk/conversations``               — list conversations
* ``GET  /api/talk/conversations/<id>``           — one conversation thread
* ``POST /api/talk/send``                         — send a message, get reply
* ``WS   /api/talk/<conversation_id>/stream``     — live message stream

Talk is the operator's direct conversation with Self Jr (the Speaker
model) — distinct from the CLI-session chat in :mod:`chat_router`, which
mirrors a ``selffork run`` round-loop. ``POST /send`` persists the
operator's message, asks the Speaker for a reply, and persists that too;
the WebSocket independently tails the store so any open cockpit sees new
messages within one poll interval (the same decoupling the chat router
uses between ``POST /messages`` and its stream).

When no Speaker endpoint is configured, or the endpoint is unreachable,
``/send`` returns ``reply=None`` with an honest ``speaker_status`` — the
cockpit renders an "offline" notice, never a fabricated reply
(``project_ui_stack`` no-mock rule).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from selffork_orchestrator.dashboard.schemas import (
    ConversationResponse,
    ConversationThreadResponse,
    TalkMessageResponse,
    TalkSendPayload,
    TalkSendResponse,
)
from selffork_orchestrator.dashboard.ws_protocol import (
    HeartbeatTask,
    WsEnvelope,
    default_registry,
    next_seq,
    parse_last_seq,
    replay_or_gap,
)
from selffork_orchestrator.talk.models import Conversation, TalkMessage, TalkRole
from selffork_orchestrator.talk.speaker import Speaker
from selffork_orchestrator.talk.store import TalkStore
from selffork_shared.errors import RuntimeUnhealthyError
from selffork_shared.logging import get_logger

__all__ = ["build_talk_router", "default_talk_db_path"]

_log = get_logger(__name__)

# Title for a freshly-created conversation: the operator's first message,
# trimmed to a glanceable length for the History list.
_TITLE_MAX_CHARS = 60

# System prompt that gives a stock (pre-fine-tune) model Self Jr's
# framing. The M7 fine-tuned adapter carries this as learned reflex and
# will not need the prompt; until then it keeps replies on-character.
_SPEAKER_SYSTEM_PROMPT = (
    "You are Self Jr, the operator's autonomous coding partner. You "
    "direct the work and reason out loud; you do not write code yourself. "
    "Reply concisely, in the operator's language."
)


def default_talk_db_path() -> Path:
    """Single-file SQLite DB holding every Talk conversation."""
    return Path("~/.selffork/talk/conversations.db").expanduser()


def build_talk_router(
    *,
    talk_db_path: Path | None = None,
    speaker: Speaker | None = None,
) -> APIRouter:
    """Return a router bound to the Talk store + Speaker.

    The :class:`TalkStore` opens lazily on the first request. ``speaker``
    is the model-endpoint client; ``None`` means no endpoint is
    configured and ``/send`` reports ``speaker_status='not_configured'``.
    """
    db_path = talk_db_path or default_talk_db_path()
    router = APIRouter(prefix="/api/talk", tags=["talk"])
    state = _TalkRouterState(db_path=db_path, speaker=speaker)
    router.state = state  # type: ignore[attr-defined]

    # ── Conversations ────────────────────────────────────────────────

    @router.get("/conversations", response_model=list[ConversationResponse])
    async def list_conversations() -> list[ConversationResponse]:
        store = await state.store()
        conversations = await store.list_conversations()
        return [_conversation_to_response(c) for c in conversations]

    @router.get(
        "/conversations/{conversation_id}",
        response_model=ConversationThreadResponse,
    )
    async def get_conversation(
        conversation_id: str,
    ) -> ConversationThreadResponse:
        store = await state.store()
        conversation = await _load_conversation(store, conversation_id)
        messages = await store.list_messages(conversation.id)
        return ConversationThreadResponse(
            conversation=_conversation_to_response(conversation),
            messages=[_message_to_response(m) for m in messages],
        )

    # ── Send ─────────────────────────────────────────────────────────

    @router.post("/send", response_model=TalkSendResponse, status_code=201)
    async def send(payload: TalkSendPayload) -> TalkSendResponse:
        if not payload.text.strip():
            raise HTTPException(status_code=400, detail="text cannot be empty")
        store = await state.store()
        conversation = await _resolve_conversation(store, payload)
        operator_message = await store.append_message(
            conversation_id=conversation.id,
            role="operator",
            content=payload.text,
        )
        reply, speaker_status = await _invoke_speaker(
            state.speaker, store, conversation.id
        )
        return TalkSendResponse(
            conversation_id=str(conversation.id),
            operator_message=_message_to_response(operator_message),
            reply=_message_to_response(reply) if reply is not None else None,
            speaker_status=speaker_status,
        )

    # ── WS message stream ────────────────────────────────────────────

    @router.websocket("/{conversation_id}/stream")
    async def stream(websocket: WebSocket, conversation_id: str) -> None:
        await websocket.accept()
        try:
            cid = UUID(conversation_id)
        except ValueError:
            await websocket.close(
                code=4400,
                reason=f"invalid conversation id {conversation_id}",
            )
            return
        store = await state.store()
        if await store.get_conversation(cid) is None:
            await websocket.close(
                code=4404,
                reason=f"conversation {conversation_id} not found",
            )
            return

        last_seq = parse_last_seq(websocket.query_params.get("last_seq"))
        registry = default_registry()
        stream_key = f"talk:{conversation_id}"
        seq_counter = registry.counter(stream_key)
        replay_buffer = registry.buffer(stream_key)

        try:
            for env in replay_or_gap(
                replay_buffer,
                last_seq=last_seq,
                seq_counter=seq_counter,
            ):
                if env.event_type == "gap":
                    replay_buffer.append(env)
                await websocket.send_text(env.model_dump_json())

            async with HeartbeatTask(
                websocket=websocket,
                seq_counter=seq_counter,
            ):
                async for message in _tail_conversation(store, cid):
                    envelope = WsEnvelope(
                        seq=next_seq(seq_counter),
                        event_type="talk.message",
                        payload={
                            "conversation_id": str(message.conversation_id),
                            "message_id": str(message.id),
                            "seq": message.seq,
                            "role": message.role,
                            "content": message.content,
                            "created_at": message.created_at.isoformat(),
                        },
                        ts=datetime.now(UTC),
                    )
                    replay_buffer.append(envelope)
                    await websocket.send_text(envelope.model_dump_json())
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _log.exception("talk_ws_failed", conversation_id=conversation_id)
            with contextlib.suppress(Exception):
                await websocket.send_text(
                    json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
                )

    return router


# ── State holder ────────────────────────────────────────────────────────────


class _TalkRouterState:
    """Per-router state — a lazily-opened store handle + the Speaker."""

    def __init__(self, *, db_path: Path, speaker: Speaker | None) -> None:
        self._db_path = db_path
        self.speaker = speaker
        self._store: TalkStore | None = None
        self._lock = asyncio.Lock()

    async def store(self) -> TalkStore:
        if self._store is not None:
            return self._store
        async with self._lock:
            if self._store is None:
                store = TalkStore(db_path=self._db_path)
                await store.setup()
                self._store = store
            return self._store

    async def teardown(self) -> None:
        async with self._lock:
            if self._store is not None:
                await self._store.teardown()
                self._store = None


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _load_conversation(
    store: TalkStore,
    conversation_id: str,
) -> Conversation:
    """Load a conversation by string id, or raise the right HTTP error."""
    try:
        cid = UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"invalid conversation id {conversation_id!r}",
        ) from exc
    conversation = await store.get_conversation(cid)
    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail=f"conversation {conversation_id!r} not found",
        )
    return conversation


async def _resolve_conversation(
    store: TalkStore,
    payload: TalkSendPayload,
) -> Conversation:
    """Continue the payload's conversation, or create a fresh one.

    With ``conversation_id`` set the existing thread is loaded (404 when
    unknown); without it a new conversation is created, scoped to
    ``workspace`` and titled from the operator's first message.
    """
    if payload.conversation_id is not None:
        return await _load_conversation(store, payload.conversation_id)
    title = payload.text.strip()[:_TITLE_MAX_CHARS] or "New conversation"
    return await store.create_conversation(
        workspace_slug=payload.workspace,
        title=title,
    )


async def _invoke_speaker(
    speaker: Speaker | None,
    store: TalkStore,
    conversation_id: UUID,
) -> tuple[TalkMessage | None, str]:
    """Ask the Speaker for a reply and persist it.

    Returns ``(reply_message, speaker_status)``. ``speaker_status`` is
    ``not_configured`` when no Speaker is wired, ``offline`` when the
    endpoint is unreachable or returns nothing usable, ``ok`` on success.
    A failure never raises — the operator message is already persisted
    and the cockpit shows an honest notice instead of a fake reply.
    """
    if speaker is None:
        return None, "not_configured"
    history = await store.list_messages(conversation_id)
    try:
        text = await speaker.reply(_build_prompt(history))
    except RuntimeUnhealthyError as exc:
        _log.warning(
            "talk_speaker_offline",
            conversation_id=str(conversation_id),
            error=str(exc),
        )
        return None, "offline"
    cleaned = text.strip()
    if not cleaned:
        return None, "offline"
    reply = await store.append_message(
        conversation_id=conversation_id,
        role="self_jr",
        content=cleaned,
    )
    return reply, "ok"


def _build_prompt(history: list[TalkMessage]) -> list[dict[str, str]]:
    """Map a Talk thread to an OpenAI-shaped message list for the Speaker.

    ``operator`` → ``user``, ``self_jr`` → ``assistant``; a system prompt
    is prepended so a stock model stays in Self Jr's character.
    """
    role_map: dict[TalkRole, str] = {
        "operator": "user",
        "self_jr": "assistant",
    }
    prompt: list[dict[str, str]] = [
        {"role": "system", "content": _SPEAKER_SYSTEM_PROMPT},
    ]
    prompt.extend(
        {"role": role_map[m.role], "content": m.content} for m in history
    )
    return prompt


async def _tail_conversation(
    store: TalkStore,
    conversation_id: UUID,
    *,
    poll_interval_seconds: float = 0.25,
) -> AsyncIterator[TalkMessage]:
    """Yield messages as they land — Phase 1 drains, Phase 2 polls.

    Mirrors the chat router's tail: a monotonic ``seq`` cursor keeps each
    poll proportional to the delta, never re-scanning the whole thread.
    """
    cursor = 0

    async def _drain() -> list[TalkMessage]:
        nonlocal cursor
        messages = await store.list_messages_after(
            conversation_id, after_seq=cursor
        )
        if messages:
            cursor = messages[-1].seq
        return messages

    for msg in await _drain():
        yield msg
    while True:
        await asyncio.sleep(poll_interval_seconds)
        for msg in await _drain():
            yield msg


def _conversation_to_response(
    conversation: Conversation,
) -> ConversationResponse:
    return ConversationResponse(
        id=str(conversation.id),
        workspace_slug=conversation.workspace_slug,
        title=conversation.title,
        created_at=conversation.created_at,
        last_message_at=conversation.last_message_at,
    )


def _message_to_response(message: TalkMessage) -> TalkMessageResponse:
    return TalkMessageResponse(
        id=str(message.id),
        conversation_id=str(message.conversation_id),
        seq=message.seq,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )
