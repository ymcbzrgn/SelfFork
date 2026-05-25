"""FastAPI router for the Talk surface — operator ↔ Self Jr — S1 + S-Stream.

Endpoints:

* ``GET  /api/talk/conversations``                                — list conversations
* ``GET  /api/talk/conversations/<id>``                            — one conversation thread
* ``POST /api/talk/send``                                          — send a message, get reply
* ``POST /api/talk/conversations/<cid>/cancel-generation/<gid>``   — stop a streaming reply
* ``WS   /api/talk/<conversation_id>/stream``                      — live message stream

Talk is the operator's direct conversation with Self Jr (the Speaker
model) — distinct from the CLI-session chat in :mod:`chat_router`, which
mirrors a ``selffork run`` round-loop.

**S1 (original):** ``POST /send`` persisted the operator message, called
``Speaker.reply()`` synchronously, persisted the reply, and returned both
messages. The WebSocket independently tailed the store via a 250 ms
poll so any open cockpit saw new messages within one tick.

**S-Stream (ADR-011 §3):** the operator's target is **CPU**, where a
single generation can take minutes-to-hours. Holding the POST request
open for the entire generation invariably trips httpx / proxy / browser
timeouts long before the reply lands. The router now:

* Persists the operator message immediately, publishes it onto a
  per-conversation broadcast channel, and returns ``speaker_status =
  "streaming"`` with a ``generation_id`` — the POST never waits for the
  reply.
* Drives :meth:`SpeakerClient.reply_stream` in an asyncio background
  task; each SSE token becomes a ``talk.token`` envelope on the channel,
  the final assistant message becomes a ``talk.message`` envelope, and
  transport/stall failures become ``talk.error`` envelopes (no fake
  reply persisted — :data:`no_mock` rule).
* Lets the operator cancel via
  ``POST /conversations/<cid>/cancel-generation/<gid>``; the task is
  cancelled, any partial text is persisted with the operator's role-tag
  so the cockpit can render the truncated reply with a cancelled badge,
  and a ``talk.cancelled`` envelope arrives on the channel.

The WebSocket no longer polls the store — it consumes the broadcast
channel directly, multiplexed through the same
:class:`~selffork_orchestrator.dashboard.ws_protocol.WsEnvelope` /
:class:`BoundedReplayBuffer` machinery as before so a reconnecting
client still resumes via ``?last_seq=``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from selffork_orchestrator.dashboard.schemas import (
    ConversationResponse,
    ConversationThreadResponse,
    TalkCancelResponse,
    TalkMessageResponse,
    TalkSendPayload,
    TalkSendResponse,
)
from selffork_orchestrator.dashboard.ws_protocol import (
    BoundedReplayBuffer,
    HeartbeatTask,
    ReplayRegistry,
    WsEnvelope,
    default_registry,
    next_seq,
    parse_last_seq,
    replay_or_gap,
)
from selffork_orchestrator.talk.models import Conversation, TalkMessage, TalkRole
from selffork_orchestrator.talk.speaker import Speaker, StreamDone, TokenChunk
from selffork_orchestrator.talk.store import TalkStore
from selffork_shared.errors import RuntimeUnhealthyError, SpeakerStalledError
from selffork_shared.logging import get_logger

__all__ = ["build_talk_router", "default_talk_db_path"]

_log = get_logger(__name__)
_py_log = logging.getLogger(__name__)

# Title for a freshly-created conversation: the operator's first message,
# trimmed to a glanceable length for the History list.
_TITLE_MAX_CHARS = 60

# Per-subscriber queue capacity. Bursts of ``talk.token`` from a fast
# generation can momentarily back up if the WS write loop is briefly
# delayed; the bounded queue plus the replay buffer give a slow consumer
# a chance to catch up via reconnect rather than blocking the streamer.
_SUBSCRIBER_QUEUE_MAX = 512

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


# ── Broadcaster ─────────────────────────────────────────────────────────────


class _TalkBroadcaster:
    """Per-conversation pub/sub channel for Talk WebSocket envelopes.

    A single broadcaster instance is shared by every WS connection +
    every streaming task on the router. ``publish()`` appends the
    envelope to the shared bounded replay buffer (so a reconnecting
    client can resume via ``?last_seq=``) AND fans it out to every live
    subscriber's queue. Slow consumers don't block the streamer — a full
    queue drops the frame; the consumer can resync by reconnecting.
    """

    def __init__(self, *, registry: ReplayRegistry) -> None:
        self._registry = registry
        self._subscribers: dict[
            str, set[asyncio.Queue[WsEnvelope]]
        ] = defaultdict(set)
        self._lock = asyncio.Lock()

    @staticmethod
    def _stream_key(conversation_id: str) -> str:
        return f"talk:{conversation_id}"

    def buffer(self, conversation_id: str) -> BoundedReplayBuffer:
        return self._registry.buffer(self._stream_key(conversation_id))

    def next_seq(self, conversation_id: str) -> int:
        return next_seq(self._registry.counter(self._stream_key(conversation_id)))

    async def subscribe(
        self, conversation_id: str
    ) -> asyncio.Queue[WsEnvelope]:
        """Register a fresh subscriber; remember to :meth:`unsubscribe`."""
        queue: asyncio.Queue[WsEnvelope] = asyncio.Queue(
            maxsize=_SUBSCRIBER_QUEUE_MAX
        )
        async with self._lock:
            self._subscribers[conversation_id].add(queue)
        return queue

    async def unsubscribe(
        self,
        conversation_id: str,
        queue: asyncio.Queue[WsEnvelope],
    ) -> None:
        async with self._lock:
            self._subscribers[conversation_id].discard(queue)
            if not self._subscribers[conversation_id]:
                self._subscribers.pop(conversation_id, None)

    async def publish(
        self,
        conversation_id: str,
        envelope: WsEnvelope,
    ) -> None:
        """Append to replay buffer + fan out to every live subscriber."""
        self.buffer(conversation_id).append(envelope)
        # Snapshot the subscriber set under the lock, fan out outside
        # (queue.put_nowait never blocks).
        async with self._lock:
            queues = list(self._subscribers.get(conversation_id, ()))
        for queue in queues:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(envelope)


# ── Router state ────────────────────────────────────────────────────────────


class _TalkRouterState:
    """Per-router state — lazily-opened store + Speaker + broadcaster.

    ``active_generations`` tracks every in-flight streaming task so the
    cancel endpoint can signal it; the streaming task removes itself
    on completion so cancel-of-already-done resolves as
    ``"already_done"`` instead of silently no-op.
    """

    def __init__(
        self,
        *,
        db_path: Path,
        speaker: Speaker | None,
        registry: ReplayRegistry,
    ) -> None:
        self._db_path = db_path
        self.speaker = speaker
        self.broadcaster = _TalkBroadcaster(registry=registry)
        self._store: TalkStore | None = None
        self._lock = asyncio.Lock()
        self._active_generations: dict[
            str, dict[str, asyncio.Task[None]]
        ] = defaultdict(dict)
        self._active_lock = asyncio.Lock()

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
        # Cancel all in-flight generations first so they don't try to
        # write to a torn-down store.
        async with self._active_lock:
            pending: list[asyncio.Task[None]] = []
            for tasks in self._active_generations.values():
                pending.extend(tasks.values())
            self._active_generations.clear()
        for task in pending:
            task.cancel()
        for task in pending:
            with contextlib.suppress(BaseException):
                await task
        async with self._lock:
            if self._store is not None:
                await self._store.teardown()
                self._store = None

    async def register_generation(
        self,
        conversation_id: str,
        generation_id: str,
        task: asyncio.Task[None],
    ) -> None:
        async with self._active_lock:
            self._active_generations[conversation_id][generation_id] = task

    async def discard_generation(
        self,
        conversation_id: str,
        generation_id: str,
    ) -> None:
        async with self._active_lock:
            tasks = self._active_generations.get(conversation_id)
            if tasks is None:
                return
            tasks.pop(generation_id, None)
            if not tasks:
                self._active_generations.pop(conversation_id, None)

    async def cancel_generation(
        self,
        conversation_id: str,
        generation_id: str,
    ) -> tuple[bool, str]:
        """Return ``(cancelled, reason)`` matching :class:`TalkCancelResponse`."""
        async with self._active_lock:
            tasks = self._active_generations.get(conversation_id)
            task = tasks.get(generation_id) if tasks is not None else None
        if task is None:
            return False, "unknown_generation"
        if task.done():
            return False, "already_done"
        task.cancel()
        return True, "cancelled"


# ── Envelope builders ───────────────────────────────────────────────────────


def _envelope(
    broadcaster: _TalkBroadcaster,
    conversation_id: str,
    *,
    event_type: str,
    payload: dict[str, object],
) -> WsEnvelope:
    return WsEnvelope(
        seq=broadcaster.next_seq(conversation_id),
        event_type=event_type,  # type: ignore[arg-type]
        payload=payload,
        ts=datetime.now(UTC),
    )


def _message_payload(message: TalkMessage) -> dict[str, object]:
    return {
        "conversation_id": str(message.conversation_id),
        "message_id": str(message.id),
        "seq": message.seq,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


# ── Streaming task ──────────────────────────────────────────────────────────


async def _stream_speaker_reply(
    *,
    state: _TalkRouterState,
    store: TalkStore,
    speaker: Speaker,
    conversation_id: UUID,
    generation_id: str,
) -> None:
    """Drive ``speaker.reply_stream`` and publish envelopes.

    Lifecycle (exactly one of these closes the stream):

    * **Success** — every token published as ``talk.token``; final
      assistant message persisted to the store + published as
      ``talk.message`` with role ``self_jr``.
    * **Transport / format / wedged-model failure** — :class:`talk.error`
      envelope with a short reason; nothing persisted (the operator
      message is already on disk so the thread is still coherent).
    * **Operator cancelled** — any partial text is persisted (so the
      cockpit can render the truncated reply with a cancelled badge);
      :class:`talk.cancelled` envelope carries the (possibly empty)
      partial text + the persisted message id when one was created.

    The task always removes itself from ``state.active_generations`` in
    a ``finally`` block so a cancel-of-already-done returns the honest
    ``"already_done"`` reason.
    """
    cid_str = str(conversation_id)
    broadcaster = state.broadcaster
    partial_chunks: list[str] = []
    try:
        history = await store.list_messages(conversation_id)
        prompt = _build_prompt(history)
        try:
            async for event in speaker.reply_stream(prompt):
                if isinstance(event, TokenChunk):
                    partial_chunks.append(event.text)
                    envelope = _envelope(
                        broadcaster,
                        cid_str,
                        event_type="talk.token",
                        payload={
                            "conversation_id": cid_str,
                            "generation_id": generation_id,
                            "text": event.text,
                        },
                    )
                    await broadcaster.publish(cid_str, envelope)
                elif isinstance(event, StreamDone):
                    full = event.full_reply.strip()
                    if not full:
                        # Honest empty: surface as error rather than
                        # persist an empty assistant message.
                        await _publish_error(
                            broadcaster,
                            cid_str,
                            generation_id,
                            kind="empty_reply",
                            detail="model returned no text",
                        )
                        return
                    message = await store.append_message(
                        conversation_id=conversation_id,
                        role="self_jr",
                        content=full,
                    )
                    envelope = _envelope(
                        broadcaster,
                        cid_str,
                        event_type="talk.message",
                        payload=_message_payload(message)
                        | {"generation_id": generation_id},
                    )
                    await broadcaster.publish(cid_str, envelope)
                    return
        except SpeakerStalledError as exc:
            await _publish_error(
                broadcaster,
                cid_str,
                generation_id,
                kind="stalled",
                detail=str(exc),
            )
            return
        except RuntimeUnhealthyError as exc:
            await _publish_error(
                broadcaster,
                cid_str,
                generation_id,
                kind="unhealthy",
                detail=str(exc),
            )
            return
    except asyncio.CancelledError:
        await _publish_cancelled(
            broadcaster,
            store,
            conversation_id,
            generation_id,
            partial="".join(partial_chunks),
        )
        raise
    except Exception as exc:  # pragma: no cover — defensive
        _py_log.exception(
            "talk_stream_unexpected", extra={"conversation_id": cid_str}
        )
        await _publish_error(
            broadcaster,
            cid_str,
            generation_id,
            kind="internal",
            detail=f"{type(exc).__name__}: {exc}",
        )
    finally:
        await state.discard_generation(cid_str, generation_id)


async def _publish_error(
    broadcaster: _TalkBroadcaster,
    conversation_id: str,
    generation_id: str,
    *,
    kind: str,
    detail: str,
) -> None:
    envelope = _envelope(
        broadcaster,
        conversation_id,
        event_type="talk.error",
        payload={
            "conversation_id": conversation_id,
            "generation_id": generation_id,
            "kind": kind,
            "detail": detail,
        },
    )
    await broadcaster.publish(conversation_id, envelope)


async def _publish_cancelled(
    broadcaster: _TalkBroadcaster,
    store: TalkStore,
    conversation_id: UUID,
    generation_id: str,
    *,
    partial: str,
) -> None:
    """Persist any partial text, then publish ``talk.cancelled``."""
    cid_str = str(conversation_id)
    cleaned = partial.strip()
    message_payload: dict[str, object] | None = None
    if cleaned:
        try:
            message = await store.append_message(
                conversation_id=conversation_id,
                role="self_jr",
                content=cleaned,
            )
        except Exception:  # pragma: no cover — store I/O during cancel
            _py_log.exception(
                "talk_cancel_persist_failed",
                extra={"conversation_id": cid_str},
            )
        else:
            message_payload = _message_payload(message)
    envelope = _envelope(
        broadcaster,
        cid_str,
        event_type="talk.cancelled",
        payload={
            "conversation_id": cid_str,
            "generation_id": generation_id,
            "partial_text": cleaned,
            "message": message_payload,
        },
    )
    await broadcaster.publish(cid_str, envelope)


# ── Router ──────────────────────────────────────────────────────────────────


def build_talk_router(
    *,
    talk_db_path: Path | None = None,
    speaker: Speaker | None = None,
    registry: ReplayRegistry | None = None,
) -> APIRouter:
    """Return a router bound to the Talk store + Speaker.

    The :class:`TalkStore` opens lazily on the first request. ``speaker``
    is the model-endpoint client; ``None`` means no endpoint is
    configured and ``/send`` reports ``speaker_status='not_configured'``.
    ``registry`` defaults to :func:`default_registry` and is exposed for
    test isolation (one per :class:`TestClient` so test cases don't
    cross-pollute via the module-global buffer).
    """
    db_path = talk_db_path or default_talk_db_path()
    router = APIRouter(prefix="/api/talk", tags=["talk"])
    state = _TalkRouterState(
        db_path=db_path,
        speaker=speaker,
        registry=registry or default_registry(),
    )
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
        cid_str = str(conversation.id)
        # Operator message goes onto the broadcast channel immediately
        # so any open WS sees it in real time.
        op_envelope = _envelope(
            state.broadcaster,
            cid_str,
            event_type="talk.message",
            payload=_message_payload(operator_message),
        )
        await state.broadcaster.publish(cid_str, op_envelope)

        if state.speaker is None:
            return TalkSendResponse(
                conversation_id=cid_str,
                operator_message=_message_to_response(operator_message),
                reply=None,
                speaker_status="not_configured",
                generation_id=None,
            )

        # Spawn the streaming task — it broadcasts talk.token /
        # talk.message / talk.error / talk.cancelled. POST returns now.
        generation_id = uuid4().hex
        task = asyncio.create_task(
            _stream_speaker_reply(
                state=state,
                store=store,
                speaker=state.speaker,
                conversation_id=conversation.id,
                generation_id=generation_id,
            )
        )
        await state.register_generation(cid_str, generation_id, task)
        return TalkSendResponse(
            conversation_id=cid_str,
            operator_message=_message_to_response(operator_message),
            reply=None,
            speaker_status="streaming",
            generation_id=generation_id,
        )

    @router.post(
        "/conversations/{conversation_id}/cancel-generation/{generation_id}",
        response_model=TalkCancelResponse,
    )
    async def cancel_generation(
        conversation_id: str, generation_id: str
    ) -> TalkCancelResponse:
        # Validate the path-id but never raise — the cancel surface is
        # idempotent and the cockpit may fire-and-forget on Stop.
        try:
            UUID(conversation_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"invalid conversation id {conversation_id!r}",
            ) from exc
        cancelled, reason = await state.cancel_generation(
            conversation_id, generation_id
        )
        return TalkCancelResponse(cancelled=cancelled, reason=reason)

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
        cid_str = conversation_id
        # Subscribe BEFORE replay so any envelope published between
        # replay-end and queue-drain is captured by both surfaces; the
        # WS loop de-duplicates via the seq cursor.
        queue = await state.broadcaster.subscribe(cid_str)
        last_sent_seq = last_seq
        replay_buffer = state.broadcaster.buffer(cid_str)
        seq_counter = state.broadcaster._registry.counter(
            f"talk:{cid_str}"
        )

        try:
            # Phase 1: replay anything the client missed.
            for env in replay_or_gap(
                replay_buffer,
                last_seq=last_seq,
                seq_counter=seq_counter,
            ):
                if env.event_type == "gap":
                    replay_buffer.append(env)
                await websocket.send_text(env.model_dump_json())
                last_sent_seq = max(last_sent_seq, env.seq)

            # Phase 2: live — drain the broadcast queue. The HeartbeatTask
            # sends keepalive pings independently so a TCP-half-open client
            # is detected within one cadence instead of the OS socket timeout.
            async with HeartbeatTask(
                websocket=websocket,
                seq_counter=seq_counter,
            ):
                while True:
                    env = await queue.get()
                    if env.seq <= last_sent_seq:
                        continue
                    await websocket.send_text(env.model_dump_json())
                    last_sent_seq = env.seq
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _log.exception("talk_ws_failed", conversation_id=cid_str)
            with contextlib.suppress(Exception):
                await websocket.send_text(
                    json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
                )
        finally:
            await state.broadcaster.unsubscribe(cid_str, queue)

    return router


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


def _build_prompt(history: Iterable[TalkMessage]) -> list[dict[str, str]]:
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
