"""FastAPI router exposing the chat surface to the cockpit — Order 4.

Endpoints:

* ``GET    /api/sessions/<id>/branches``                — list branches
* ``GET    /api/sessions/<id>/messages``                — list current branch
* ``POST   /api/sessions/<id>/messages``                — append message
* ``POST   /api/sessions/<id>/messages/<msg_id>/edit``  — fork branch + append
* ``PATCH  /api/sessions/<id>/active-branch``           — switch branch
* ``WS     /api/sessions/<id>/chat/stream``             — live chat events

The router opens a per-session :class:`BranchStore` that is shared
across requests for the lifetime of the FastAPI app (one SQLite file
holds every session's branches). This avoids the per-request
connection cost SQLite would otherwise pay on every cockpit click.

Edits create a *new* branch (assistant-ui semantics — immutable
history) and additionally write a ``mind.note.alternative_path`` in
the project's Mind store so the operator can audit what was edited
out (memory: ``project_done_sentinel_protocol`` + Order 4 §M-4).
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from selffork_mind.memory.model import Note
from selffork_orchestrator.chat.branch_model import (
    Branch,
    ChatMessage,
    MessageRole,
)
from selffork_orchestrator.chat.branch_store import BranchStore
from selffork_orchestrator.dashboard.mind_deps import (
    open_store as open_mind_store,
)
from selffork_orchestrator.dashboard.mind_deps import (
    resolve_mind_root,
)
from selffork_orchestrator.dashboard.schemas import (
    ActiveBranchPayload,
    BranchResponse,
    ChatMessageEditPayload,
    ChatMessagePayload,
    ChatMessageResponse,
)
from selffork_orchestrator.dashboard.ws_protocol import (
    HeartbeatTask,
    WsEnvelope,
    default_registry,
    next_seq,
    parse_last_seq,
    replay_or_gap,
)
from selffork_shared.config import MindConfig
from selffork_shared.errors import ConfigError
from selffork_shared.logging import get_logger

__all__ = ["ProjectSlugResolver", "build_chat_router", "default_chat_db_path"]

_log = get_logger(__name__)

# Resolver returns the project slug a session belongs to, or ``None``
# for orphan (non-project) sessions. The dashboard wires this from
# ``_resolve_audit_dir`` so the chat router can land Mind T2
# alternative-path notes in the right per-project Mind store.
type ProjectSlugResolver = Callable[[str], "str | None"]


def default_chat_db_path() -> Path:
    """Single-file SQLite DB shared across every session's branches."""
    return Path("~/.selffork/chat/branches.db").expanduser()


def build_chat_router(
    *,
    chat_db_path: Path | None = None,
    mind_config: MindConfig | None = None,
    project_slug_resolver: ProjectSlugResolver | None = None,
) -> APIRouter:
    """Return a router bound to the chat store path + Mind config.

    The returned router opens its :class:`BranchStore` lazily on the
    first request that needs it, then keeps it open for the rest of
    the FastAPI process lifetime. Tests close it via the lifespan
    cleanup hook the dashboard server registers.
    """
    db_path = chat_db_path or default_chat_db_path()
    router = APIRouter(prefix="/api/sessions/{session_id}", tags=["chat"])
    state = _ChatRouterState(
        db_path=db_path,
        mind_config=mind_config,
        project_slug_resolver=project_slug_resolver,
    )
    # The store stays open for the FastAPI process lifetime; the OS
    # reaps the SQLite file handle on exit. Tests sharing the same
    # process state should never collide because each test gets its
    # own ``chat_db_path`` under ``tmp_path``. (We deliberately don't
    # use ``router.on_event("shutdown")`` — Starlette deprecated it
    # in favour of lifespan handlers, but those need to be wired on
    # the parent ``FastAPI`` instance and we want this router to be
    # plug-and-play across multiple apps in tests.)
    router.state = state  # type: ignore[attr-defined]

    # ── Branches ─────────────────────────────────────────────────────

    @router.get("/branches", response_model=list[BranchResponse])
    async def list_branches(session_id: str) -> list[BranchResponse]:
        store = await state.store()
        branches = await store.list_branches(session_id)
        return [_branch_to_response(b) for b in branches]

    @router.patch("/active-branch", response_model=BranchResponse)
    async def set_active_branch(
        session_id: str,
        payload: ActiveBranchPayload,
    ) -> BranchResponse:
        try:
            branch_id = UUID(payload.branch_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"invalid branch_id {payload.branch_id!r}",
            ) from exc
        store = await state.store()
        try:
            updated = await store.set_active_branch(session_id, branch_id)
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _branch_to_response(updated)

    # ── Messages ─────────────────────────────────────────────────────

    @router.get(
        "/messages",
        response_model=list[ChatMessageResponse],
    )
    async def list_messages(
        session_id: str,
        branch_id: str | None = None,
    ) -> list[ChatMessageResponse]:
        store = await state.store()
        target = await _resolve_branch(store, session_id, branch_id)
        if target is None:
            return []
        msgs = await store.list_messages(target.id)
        return [_message_to_response(m) for m in msgs]

    @router.post(
        "/messages",
        response_model=ChatMessageResponse,
        status_code=201,
    )
    async def post_message(
        session_id: str,
        payload: ChatMessagePayload,
    ) -> ChatMessageResponse:
        if payload.role not in {"user", "assistant", "tool"}:
            raise HTTPException(
                status_code=400,
                detail=f"invalid role {payload.role!r}",
            )
        store = await state.store()
        branch = await _resolve_or_seed_branch(
            store, session_id, payload.branch_id
        )
        try:
            message = await store.append_message(
                branch_id=branch.id,
                role=cast("MessageRole", payload.role),
                content=payload.content,
            )
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _message_to_response(message)

    @router.post(
        "/messages/{message_id}/edit",
        response_model=BranchResponse,
        status_code=201,
    )
    async def edit_message(
        session_id: str,
        message_id: str,
        payload: ChatMessageEditPayload,
    ) -> BranchResponse:
        try:
            mid = UUID(message_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"invalid message_id {message_id!r}",
            ) from exc
        store = await state.store()
        label = (
            payload.branch_label
            if payload.branch_label and payload.branch_label.strip()
            else f"alt-{mid.hex[:8]}"
        )
        try:
            new_branch, _prefix = await store.fork_from_message(
                session_id=session_id,
                message_id=mid,
                label=label,
                activate=True,
            )
        except ConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            await store.append_message(
                branch_id=new_branch.id,
                role="user",
                content=payload.content,
            )
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # M-4 — Mind T2 alternative-path log so the operator can audit
        # which branches were forked from where post-hoc. Best-effort:
        # a Mind write failure must not roll back the branch (the user
        # already saw "edit succeeded" in the UI).
        await _log_alternative_path(
            mind_config=state.mind_config,
            project_slug_resolver=state.project_slug_resolver,
            session_id=session_id,
            new_branch_id=new_branch.id,
            fork_message_id=mid,
            label=label,
        )
        return _branch_to_response(new_branch)

    # ── WS chat stream ───────────────────────────────────────────────

    @router.websocket("/chat/stream")
    async def chat_stream(websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()

        last_seq = parse_last_seq(websocket.query_params.get("last_seq"))
        registry = default_registry()
        stream_key = f"chat:{session_id}"
        seq_counter = registry.counter(stream_key)
        replay_buffer = registry.buffer(stream_key)

        store = await state.store()

        try:
            for env in replay_or_gap(
                replay_buffer,
                last_seq=last_seq,
                seq_counter=seq_counter,
                session_id=session_id,
            ):
                if env.event_type == "gap":
                    replay_buffer.append(env)
                await websocket.send_text(env.model_dump_json())

            async with HeartbeatTask(
                websocket=websocket,
                seq_counter=seq_counter,
                session_id=session_id,
            ):
                async for message in _tail_session_messages(store, session_id):
                    envelope = WsEnvelope(
                        seq=next_seq(seq_counter),
                        # Note: this is currently message-level, not
                        # token-level — the orchestrator's round-loop
                        # surfaces complete Jr replies. Token streaming
                        # is M5+ scope; the wire name stays for forward
                        # compatibility.
                        event_type="chat.token",
                        session_id=session_id,
                        payload={
                            "message_id": str(message.id),
                            "branch_id": str(message.branch_id),
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
            _log.exception("chat_ws_failed", session_id=session_id)
            with contextlib.suppress(Exception):
                await websocket.send_text(
                    json.dumps(
                        {"error": f"{type(exc).__name__}: {exc}"},
                    ),
                )

    return router


# ── State holder ────────────────────────────────────────────────────────────


class _ChatRouterState:
    """Per-router state — store handle + Mind config + project resolver."""

    def __init__(
        self,
        *,
        db_path: Path,
        mind_config: MindConfig | None,
        project_slug_resolver: ProjectSlugResolver | None,
    ) -> None:
        self._db_path = db_path
        self.mind_config = mind_config
        self.project_slug_resolver = project_slug_resolver
        self._store: BranchStore | None = None
        self._lock = asyncio.Lock()

    async def store(self) -> BranchStore:
        if self._store is not None:
            return self._store
        async with self._lock:
            if self._store is None:
                store = BranchStore(db_path=self._db_path)
                await store.setup()
                self._store = store
            return self._store

    async def teardown(self) -> None:
        async with self._lock:
            if self._store is not None:
                await self._store.teardown()
                self._store = None


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _resolve_branch(
    store: BranchStore,
    session_id: str,
    branch_id: str | None,
) -> Branch | None:
    if branch_id is not None:
        try:
            uid = UUID(branch_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"invalid branch_id {branch_id!r}",
            ) from exc
        branch = await store.get_branch(uid)
        if branch is None or branch.session_id != session_id:
            raise HTTPException(
                status_code=404,
                detail=f"branch {branch_id!r} not in session {session_id!r}",
            )
        return branch
    return await store.get_active_branch(session_id)


async def _resolve_or_seed_branch(
    store: BranchStore,
    session_id: str,
    branch_id: str | None,
) -> Branch:
    branch = await _resolve_branch(store, session_id, branch_id)
    if branch is not None:
        return branch
    # First message on a fresh session — seed a ``main`` branch so the
    # cockpit doesn't have to special-case "click 'New chat' first".
    return await store.create_branch(session_id=session_id, label="main")


async def _log_alternative_path(
    *,
    mind_config: MindConfig | None,
    project_slug_resolver: ProjectSlugResolver | None,
    session_id: str,
    new_branch_id: UUID,
    fork_message_id: UUID,
    label: str,
) -> _AltPathOutcome:
    """Write a Mind T2 alternative-path note for a fork; never raises.

    Order 4 audit Finding #3 fix: returns a structured outcome so the
    caller can emit an observability audit event when the Mind write
    is skipped or fails — pre-fix the branch was committed and the
    Mind side just disappeared on the floor with a ``_log.warning``.
    Now the API caller knows which branch lacked its Mind log and
    can surface it post-hoc.
    """
    if mind_config is None or project_slug_resolver is None:
        return _AltPathOutcome(status="skipped", reason="no_mind_config")
    try:
        slug = project_slug_resolver(session_id)
    except Exception as exc:
        _log.warning(
            "chat_alt_path_resolver_failed",
            session_id=session_id,
        )
        return _AltPathOutcome(
            status="failed", reason=f"resolver_exc:{type(exc).__name__}",
        )
    if slug is None:
        return _AltPathOutcome(status="skipped", reason="orphan_session")
    root = resolve_mind_root(config=mind_config, project_slug=slug)
    try:
        store = await open_mind_store(root=root)
    except Exception as exc:
        _log.warning(
            "chat_alt_path_mind_open_failed",
            session_id=session_id,
            project_slug=slug,
        )
        return _AltPathOutcome(
            status="failed",
            reason=f"open_store_exc:{type(exc).__name__}",
            project_slug=slug,
        )
    try:
        note = Note(
            tier="episodic",
            kind="observation",
            content=(
                f"Branch fork: new branch {new_branch_id!s} "
                f"created from message {fork_message_id!s} "
                f"with label {label!r}."
            ),
            intent="branch_creation",
            project_slug=slug,
            session_id=session_id,
            tag_keys=("branch_id", "fork_message_id"),
        )
        try:
            await store.upsert_note(note)
        except Exception as exc:
            _log.warning(
                "chat_alt_path_upsert_failed",
                session_id=session_id,
                project_slug=slug,
            )
            return _AltPathOutcome(
                status="failed",
                reason=f"upsert_exc:{type(exc).__name__}",
                project_slug=slug,
            )
    finally:
        await store.teardown()
    return _AltPathOutcome(
        status="ok", reason=None, project_slug=slug, note_id=str(note.id),
    )


@dataclasses.dataclass(frozen=True, slots=True)
class _AltPathOutcome:
    status: Literal["ok", "skipped", "failed"]
    reason: str | None = None
    project_slug: str | None = None
    note_id: str | None = None


async def _tail_session_messages(
    store: BranchStore,
    session_id: str,
    *,
    poll_interval_seconds: float = 0.25,
) -> AsyncIterator[ChatMessage]:
    """Poll the store for new messages across all of the session's branches.

    Phase 1 drains everything that already exists; Phase 2 picks up
    appends. Order 4 audit Finding #2 fix: previous implementation
    held an unbounded ``set[UUID]`` of seen IDs and re-scanned every
    branch on every poll (O(B*M) per tick, monotonic memory growth on
    long-lived connections). New implementation tracks a per-branch
    ``max(created_at)`` cursor and asks the store for rows strictly
    after that timestamp — bounded memory, work proportional only to
    the *delta* since the last poll.
    """
    cursor_by_branch: dict[UUID, datetime] = {}

    async def _drain() -> list[ChatMessage]:
        out: list[ChatMessage] = []
        for branch in await store.list_branches(session_id):
            after = cursor_by_branch.get(branch.id)
            messages = await store.list_messages_after(
                branch.id, after=after,
            )
            if messages:
                cursor_by_branch[branch.id] = messages[-1].created_at
                out.extend(messages)
        return out

    # Phase 1 — initial drain.
    for msg in await _drain():
        yield msg

    # Phase 2 — poll for appends.
    while True:
        await asyncio.sleep(poll_interval_seconds)
        for msg in await _drain():
            yield msg


def _branch_to_response(branch: Branch) -> BranchResponse:
    return BranchResponse(
        id=str(branch.id),
        session_id=branch.session_id,
        parent_branch_id=(
            str(branch.parent_branch_id)
            if branch.parent_branch_id
            else None
        ),
        fork_message_id=(
            str(branch.fork_message_id)
            if branch.fork_message_id
            else None
        ),
        label=branch.label,
        is_active=branch.is_active,
        created_at=branch.created_at,
    )


def _message_to_response(message: ChatMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=str(message.id),
        branch_id=str(message.branch_id),
        role=message.role,
        content=message.content,
        parent_message_id=(
            str(message.parent_message_id)
            if message.parent_message_id
            else None
        ),
        created_at=message.created_at,
    )
