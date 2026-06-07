"""FastAPI router exposing Mind to the cockpit Context tab — Order 3.

Endpoints:

* ``GET    /api/projects/<slug>/mind/stats``       — per-tier counts + recency
* ``GET    /api/projects/<slug>/mind/notes``       — paginated list (tier filter)
* ``GET    /api/projects/<slug>/mind/notes/<id>``  — single note detail
* ``POST   /api/projects/<slug>/mind/notes``       — create (mirror of mind_note_add tool)
* ``DELETE /api/projects/<slug>/mind/notes/<id>``  — supersede (writes valid_until)
* ``POST   /api/projects/<slug>/mind/recall``      — RetrieveConfig projection
* ``WS     /api/projects/<slug>/mind/provenance/stream`` — live JSONL tail

Per ``project_ui_stack.md``: zero mock data. Each endpoint opens a real
:class:`DuckDBMindStore` backed by ``~/.selffork/projects/<slug>/mind/notes.duckdb``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from selffork_mind.memory.model import Note, NoteKind, TierName
from selffork_mind.memory.tags import Tag
from selffork_mind.store.base import RetrieveConfig, StoreScope
from selffork_mind.store.duckdb import DuckDBMindStore
from selffork_orchestrator.dashboard.mind_deps import (
    build_embedder_or_none,
    open_store,
    resolve_mind_root,
)
from selffork_orchestrator.dashboard.schemas import (
    MindNoteCreatePayload,
    MindNoteUpdatePayload,
    MindRecallRequestPayload,
    MindRecallResponse,
    MindStatsResponse,
    MindTierStatsRow,
    NoteResponse,
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
from selffork_shared.logging import get_logger

__all__ = ["build_mind_router"]

_log = get_logger(__name__)

# 0.5 s feels live in the cockpit without thrashing fsstat() on idle
# projects (matches the kanban WS poll interval).
_PROVENANCE_POLL_INTERVAL_SECONDS = 0.5

_VALID_TIERS: frozenset[str] = frozenset(
    {
        "working",
        "episodic",
        "semantic_graph",
        "procedural",
        "reflection",
        "recall",
    },
)
_VALID_KINDS: frozenset[str] = frozenset(
    {"decision", "observation", "pattern", "reflection", "pointer"},
)


def build_mind_router(*, mind_config: MindConfig) -> APIRouter:
    """Return a router bound to a concrete :class:`MindConfig`.

    The router opens (and tears down) its own DuckDB store per request.
    Holding a long-lived store on the FastAPI app would require a
    shutdown hook + lock contention against ``selffork mind`` CLI
    invocations writing to the same file; per-request setup is
    cheap (DuckDB opens a file handle, no migrations).
    """
    router = APIRouter(prefix="/api/projects/{slug}/mind", tags=["mind"])

    # ── Stats ──────────────────────────────────────────────────────────

    @router.get("/stats", response_model=MindStatsResponse)
    async def mind_stats(slug: str) -> MindStatsResponse:
        async with _scoped_store(mind_config, slug) as store:
            stats = await store.count_by_tier(StoreScope(project_slug=slug))
        return MindStatsResponse(
            tiers={
                tier: MindTierStatsRow(
                    count=row.count,
                    last_updated=row.last_updated,
                )
                for tier, row in stats.items()
            },
        )

    # ── Notes (list + detail + create + supersede) ─────────────────────

    @router.get("/notes", response_model=list[NoteResponse])
    async def list_notes(
        slug: str,
        tier: str | None = None,
        limit: int = 50,
    ) -> list[NoteResponse]:
        if tier is not None and tier not in _VALID_TIERS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown tier {tier!r}; expected one of {sorted(_VALID_TIERS)}",
            )
        if limit <= 0 or limit > 1000:
            raise HTTPException(
                status_code=400,
                detail="limit must be in [1, 1000]",
            )
        tiers: tuple[TierName, ...] = (cast(TierName, tier),) if tier is not None else ()
        config = RetrieveConfig(
            tiers=tiers,
            scope=StoreScope(project_slug=slug),
            top_k=limit,
            rerank_overfetch=1,
        )
        async with _scoped_store(mind_config, slug) as store:
            hits = await store.retrieve(config)
        return [_note_to_response(h.note) for h in hits]

    @router.get("/notes/{note_id}", response_model=NoteResponse)
    async def get_note(slug: str, note_id: str) -> NoteResponse:
        try:
            uid = UUID(note_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"invalid note id {note_id!r}: {exc}",
            ) from exc
        async with _scoped_store(mind_config, slug) as store:
            note = await store.get_note(uid)
        if note is None:
            raise HTTPException(
                status_code=404,
                detail=f"note {note_id!r} not found in project {slug!r}",
            )
        # Note belongs to a different project — refuse to leak across slugs.
        if note.project_slug not in (None, slug):
            raise HTTPException(
                status_code=404,
                detail=f"note {note_id!r} not found in project {slug!r}",
            )
        return _note_to_response(note)

    @router.post(
        "/notes",
        response_model=NoteResponse,
        status_code=201,
    )
    async def create_note(
        slug: str,
        payload: MindNoteCreatePayload,
    ) -> NoteResponse:
        if payload.tier not in _VALID_TIERS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown tier {payload.tier!r}",
            )
        if payload.kind not in _VALID_KINDS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown kind {payload.kind!r}",
            )
        if not payload.content.strip():
            raise HTTPException(
                status_code=400,
                detail="content cannot be empty",
            )
        note = Note(
            tier=cast(TierName, payload.tier),
            kind=cast(NoteKind, payload.kind),
            content=payload.content,
            intent=payload.intent,
            importance=payload.importance,
            pinned=payload.pinned,
            project_slug=slug,
            session_id=payload.session_id,
            tag_keys=tuple(k for k, _ in payload.tag_pairs),
        )
        async with _scoped_store(mind_config, slug) as store:
            stored = await store.upsert_note(note)
            if payload.tag_pairs:
                tags = [Tag.now(note_id=stored.id, key=k, value=v) for k, v in payload.tag_pairs]
                await store.attach_tags(tags)
        return _note_to_response(stored)

    @router.delete("/notes/{note_id}", status_code=204)
    async def supersede_note(slug: str, note_id: str) -> None:
        try:
            uid = UUID(note_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"invalid note id {note_id!r}: {exc}",
            ) from exc
        async with _scoped_store(mind_config, slug) as store:
            note = await store.get_note(uid)
            if note is None or note.project_slug not in (None, slug):
                raise HTTPException(
                    status_code=404,
                    detail=f"note {note_id!r} not found in project {slug!r}",
                )
            await store.supersede(uid)

    @router.patch("/notes/{note_id}", response_model=NoteResponse)
    async def update_note(
        slug: str,
        note_id: str,
        payload: MindNoteUpdatePayload,
    ) -> NoteResponse:
        """S7 — atomic supersede + create.

        Operator-facing in-place edit on top of the Mind T2 bi-temporal
        supersede pattern: marks the existing note ``valid_until=now``
        and writes a fresh row with the patched fields. Tier, kind,
        ``session_id`` and ``tag_keys`` are carried forward from the
        superseded note so the operator only patches content / intent /
        importance / pinned. Returns the new note row.
        """
        try:
            uid = UUID(note_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"invalid note id {note_id!r}: {exc}",
            ) from exc
        # Reject a fully-empty patch — defensive against accidental
        # debounce calls firing with stale empty state.
        if all(
            getattr(payload, name) is None for name in ("content", "intent", "importance", "pinned")
        ):
            raise HTTPException(
                status_code=400,
                detail="patch is empty — at least one field must be provided",
            )
        async with _scoped_store(mind_config, slug) as store:
            old = await store.get_note(uid)
            if old is None or old.project_slug not in (None, slug):
                raise HTTPException(
                    status_code=404,
                    detail=f"note {note_id!r} not found in project {slug!r}",
                )
            new_content = payload.content if payload.content is not None else old.content
            if not new_content.strip():
                raise HTTPException(
                    status_code=400,
                    detail="content cannot be empty",
                )
            # Force a fresh UUID for the new row. Without this, the
            # Note model derives id from
            # ``identity_fields=("tier","content_hash","session_id")``
            # (Note.identity_fields in memory/model.py); an
            # intent / importance / pinned-only PATCH leaves all three
            # identity bits unchanged, so the auto-derived UUID5
            # collides with the superseded row and ``upsert_note``
            # would overwrite the just-set ``valid_until`` back to
            # ``None`` (audit-god S7 Finding #1, 2026-05-24).
            new_note = Note(
                id=uuid4(),
                tier=old.tier,
                kind=old.kind,
                content=new_content,
                intent=payload.intent if payload.intent is not None else old.intent,
                importance=payload.importance if payload.importance is not None else old.importance,
                pinned=payload.pinned if payload.pinned is not None else old.pinned,
                project_slug=slug,
                session_id=old.session_id,
                tag_keys=old.tag_keys,
            )
            # Supersede + create as a pair. If the upsert raises after
            # supersede succeeded, attempt a best-effort revert of the
            # supersede so the operator's previous version is not lost.
            # Full single-statement transactional atomicity would
            # require store-level support — out of S7 scope; the revert
            # path covers the realistic failure modes (validation error
            # on Note pydantic, transient DB read failure).
            await store.supersede(uid)
            try:
                stored = await store.upsert_note(new_note)
            except Exception:
                # Re-resurrect the previous row by writing the same
                # note shape back with ``valid_until=None``. The id
                # matches (UUID5 from identity) so this is an in-place
                # update — no orphan rows.
                with contextlib.suppress(Exception):
                    await store.upsert_note(old)
                raise
            return _note_to_response(stored)

    # ── Recall ─────────────────────────────────────────────────────────

    @router.post("/recall", response_model=MindRecallResponse)
    async def recall(
        slug: str,
        payload: MindRecallRequestPayload,
    ) -> MindRecallResponse:
        if payload.tier is not None and payload.tier not in _VALID_TIERS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown tier {payload.tier!r}",
            )
        if payload.top_k <= 0 or payload.top_k > 200:
            raise HTTPException(
                status_code=400,
                detail="top_k must be in [1, 200]",
            )
        tiers: tuple[TierName, ...] = (
            (cast(TierName, payload.tier),) if payload.tier is not None else ()
        )
        tag_pairs: tuple[tuple[str, str], ...] = tuple((k, v) for k, v in payload.tag_pairs)
        # When the operator configures a real embedder, embed the query
        # so the store runs vector cosine search instead of falling back
        # to the recency-weighted baseline. ``mind.embedder = "none"``
        # keeps BM25/filter-only retrieval (Order 3 default).
        # Order 3 audit Finding #1: previously the router silently
        # ignored ``mind_config.embedder`` regardless of user config.
        query_embedding: tuple[float, ...] | None = None
        if payload.query.strip():
            embedder = build_embedder_or_none(mind_config)
            if embedder is not None:
                vector = await embedder.embed_query(payload.query)
                query_embedding = tuple(vector)
        config = RetrieveConfig(
            tiers=tiers,
            scope=StoreScope(
                project_slug=slug,
                session_id=payload.session_id,
            ),
            tag_pairs=tag_pairs,
            top_k=payload.top_k,
            query_embedding=query_embedding,
        )
        async with _scoped_store(mind_config, slug) as store:
            hits = await store.retrieve(config)
        # Threshold filter — for filter-only matches the score is the
        # store's recency-weighted baseline; with an embedder it's the
        # cosine similarity.
        filtered = [h for h in hits if h.score >= payload.threshold]
        return MindRecallResponse(
            hits=[_note_to_response(h.note) for h in filtered],
            scores=[h.score for h in filtered],
        )

    # ── Provenance live tail (WS) ──────────────────────────────────────

    @router.websocket("/provenance/stream")
    async def provenance_stream(websocket: WebSocket, slug: str) -> None:
        # ``Path("~/...").expanduser()`` is sync but does no I/O (just
        # ``$HOME`` lookup + string join), so ASYNC240's "no blocking
        # pathlib in async context" warning is a false positive here.
        projects_root = Path("~/.selffork/projects").expanduser()  # noqa: ASYNC240
        log_path = projects_root / slug / "mind" / "provenance.jsonl"
        await websocket.accept()

        last_seq = parse_last_seq(websocket.query_params.get("last_seq"))
        registry = default_registry()
        stream_key = f"mind-provenance:{slug}"
        seq_counter = registry.counter(stream_key)
        replay_buffer = registry.buffer(stream_key)

        try:
            for env in replay_or_gap(
                replay_buffer,
                last_seq=last_seq,
                seq_counter=seq_counter,
                project_slug=slug,
            ):
                if env.event_type == "gap":
                    replay_buffer.append(env)
                await websocket.send_text(env.model_dump_json())

            async with HeartbeatTask(
                websocket=websocket,
                seq_counter=seq_counter,
                project_slug=slug,
            ):
                async for entry in _tail_provenance(log_path):
                    envelope = WsEnvelope(
                        seq=next_seq(seq_counter),
                        event_type="mind",
                        project_slug=slug,
                        payload=entry,
                        ts=datetime.now(UTC),
                    )
                    replay_buffer.append(envelope)
                    await websocket.send_text(envelope.model_dump_json())
            # Heartbeat envelopes also share the seq counter; we don't
            # buffer them (they carry no data), so post-tail bookkeeping
            # only needs to ensure the heartbeat task tore down — that
            # happens via the ``async with HeartbeatTask`` exit above.
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _log.exception("mind_provenance_ws_failed", project_slug=slug)
            with contextlib.suppress(Exception):
                await websocket.send_text(
                    json.dumps(
                        {"error": f"{type(exc).__name__}: {exc}"},
                    ),
                )

    return router


# ── Helpers ─────────────────────────────────────────────────────────────────


@contextlib.asynccontextmanager
async def _scoped_store(
    config: MindConfig,
    slug: str,
) -> AsyncIterator[DuckDBMindStore]:
    """Open a per-project DuckDB store for the duration of one request."""
    root = resolve_mind_root(config=config, project_slug=slug)
    store = await open_store(root=root)
    try:
        yield store
    finally:
        await store.teardown()


def _note_to_response(note: Note) -> NoteResponse:
    """Project a :class:`Note` to the wire schema (UUID→str, tuples→lists)."""
    return NoteResponse(
        id=str(note.id),
        tier=note.tier,
        kind=note.kind,
        content=note.content,
        intent=note.intent,
        importance=note.importance,
        pinned=note.pinned,
        project_slug=note.project_slug,
        session_id=note.session_id,
        valid_from=note.valid_from,
        valid_until=note.valid_until,
        tag_keys=list(note.tag_keys),
        path_scope=list(note.path_scope),
        always_apply=note.always_apply,
    )


async def _tail_provenance(log_path: Path) -> AsyncIterator[dict[str, object]]:
    """``tail -F`` of a ProvenanceRecorder JSONL log. Skips malformed lines.

    Mirrors the audit-reader tail pattern — Phase 1 wait for the file
    to appear, Phase 2 drain existing lines, Phase 3 poll for appends.
    """
    while not log_path.is_file():  # noqa: ASYNC110, ASYNC240
        await asyncio.sleep(_PROVENANCE_POLL_INTERVAL_SECONDS)

    with log_path.open(encoding="utf-8") as f:
        for line in f:
            payload = _parse_jsonl_line(line)
            if payload is not None:
                yield payload

        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(_PROVENANCE_POLL_INTERVAL_SECONDS)
                continue
            payload = _parse_jsonl_line(line)
            if payload is not None:
                yield payload


def _parse_jsonl_line(line: str) -> dict[str, object] | None:
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj
