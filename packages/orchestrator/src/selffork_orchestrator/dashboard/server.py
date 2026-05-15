"""FastAPI app for the SelfFork dashboard.

Reads real on-disk artifacts (audit JSONL, ScheduledResumeStore,
plan.json, workspace dirs) and exposes them over HTTP + WebSocket.
ABSOLUTELY no mock data — see ``project_ui_stack.md``.

The app factory :func:`build_app` accepts a :class:`DashboardConfig`
so tests can point it at fixture directories. Production callers
(``selffork ui``) build it from the user's :class:`SelfForkSettings`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import anyio
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from selffork_mind.projections.provenance import ProvenanceRecorder
from selffork_orchestrator.dashboard.audit_reader import (
    list_recent_sessions,
    read_session_events,
    tail_session_events,
)
from selffork_orchestrator.dashboard.schemas import (
    AuditEvent,
    CardCreatePayload,
    CardMovePayload,
    CardUpdatePayload,
    KanbanCardResponse,
    KanbanResponse,
    PausedSession,
    PlanSnapshot,
    ProjectCreatePayload,
    ProjectResponse,
    ProvenanceEntryResponse,
    RecentSession,
    RunRequestPayload,
    RunRequestResponse,
    WorkspaceEntry,
)
from selffork_orchestrator.dashboard.ws_protocol import (
    HeartbeatTask,
    build_audit_envelope,
    default_registry,
    next_seq,
    parse_last_seq,
    replay_or_gap,
)
from selffork_orchestrator.projects.model import (
    DEFAULT_COLUMNS,
    KanbanBoard,
    KanbanCard,
    KanbanColumn,
)
from selffork_orchestrator.projects.store import _SENTINEL, ProjectStore
from selffork_orchestrator.resume.store import ScheduledResumeStore
from selffork_orchestrator.usage.aggregator import (
    UsageAggregator,
    UsageAggregatorConfig,
)
from selffork_orchestrator.usage.model import ProviderUsage
from selffork_shared.config import MindConfig
from selffork_shared.errors import ConfigError
from selffork_shared.logging import get_logger

__all__ = ["DashboardConfig", "build_app"]

_log = get_logger(__name__)

# Number of recent sessions returned by ``GET /api/sessions/recent``.
# 50 is enough for a dashboard list without paginating.
_RECENT_LIMIT = 50

# How often the kanban WebSocket re-reads the board file. 0.5s feels
# instant in the UI without thrashing the disk for an idle project.
_KANBAN_POLL_INTERVAL_SECONDS = 0.5

# Cap workspace listing depth so ``ls -R`` on a huge tree doesn't pin
# the dashboard event loop. Files past this depth are silently skipped.
_WORKSPACE_MAX_DEPTH = 3
_WORKSPACE_MAX_ENTRIES = 500


class DashboardConfig(BaseModel):
    """Inputs the dashboard server needs to read real artifacts.

    Attributes:
        audit_dir: where ``AuditLogger`` writes session JSONL files
            for orphan (non-project) sessions.
        resume_dir: ``~/.selffork/scheduled``-style directory.
        projects_root: ``~/.selffork/projects/``-style root holding
            per-project subdirectories.
        selffork_script: absolute path to the ``selffork`` console
            script. Used by ``POST /api/sessions/run`` and the resume
            action — we shell out to it rather than re-implementing
            the orchestrator inside the dashboard process.
        static_dir: Path to the built Next.js bundle (``out/``). When
            ``None``, the dashboard serves only the API; the Next.js
            dev server is responsible for the frontend.
    """

    audit_dir: Path
    resume_dir: Path
    projects_root: Path
    selffork_script: Path
    static_dir: Path | None = None
    # Mind pillar config — the cockpit Context tab + ``mind_router``
    # endpoints rely on this. Default keeps the orphan layout
    # (``~/.selffork/mind``) and the safe ``embedder='none'`` BM25-only
    # mode (Order 3 — the cockpit's recall query never has to wait on
    # an embedding model download to come back).
    mind_config: MindConfig = MindConfig()
    # Chat surface SQLite DB path. ``None`` falls back to
    # ``~/.selffork/chat/branches.db`` (Order 4). Tests point this at a
    # tmp_path file so each test starts from a clean branch tree.
    chat_db_path: Path | None = None
    # Path to ``selffork.yaml``. Cockpit Settings → Vision writes the
    # ``vision:`` section back here. ``None`` disables persistent
    # updates (``POST /api/settings/vision`` returns 503).
    config_path: Path | None = None


def build_app(config: DashboardConfig) -> FastAPI:
    """Construct the FastAPI app bound to a concrete config.

    Pure factory — no side effects on import.
    """
    app = FastAPI(
        title="SelfFork Dashboard",
        version="0.1.0",
        description=(
            "Read-only views over real SelfFork artifacts on disk. "
            "ABSOLUTELY no mock data — see project_ui_stack.md."
        ),
    )
    # Permissive CORS for local dev (Next.js dev server on a different
    # port). Production static-export build is same-origin so this has
    # no effect there.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_api_routes(app, config)
    # Mind cockpit endpoints — Order 3 (mind_router).
    from selffork_orchestrator.dashboard.mind_router import build_mind_router

    app.include_router(build_mind_router(mind_config=config.mind_config))

    # Chat surface — Order 4 (chat_router).
    from selffork_orchestrator.dashboard.chat_router import build_chat_router

    def _resolve_project_for_session(session_id: str) -> str | None:
        # Audit-dir resolver locates the project the session belongs to;
        # ``None`` for orphan sessions (no Mind alt-path log gets written
        # because there's no per-project Mind store to write to).
        audit_dir = _resolve_audit_dir(config, session_id)
        if audit_dir is None or not config.projects_root.exists():
            return None
        try:
            relative = audit_dir.relative_to(config.projects_root)
        except ValueError:
            return None
        return relative.parts[0] if relative.parts else None

    app.include_router(
        build_chat_router(
            chat_db_path=config.chat_db_path,
            mind_config=config.mind_config,
            project_slug_resolver=_resolve_project_for_session,
        ),
    )

    # M5 Order 8 + Order 9 — Body Fleet + Provider Auth UI + Body Sessions.
    # Lazy imports keep import-time cost low for non-M5 deployments.
    from selffork_body.sandbox import BodyWatchdog
    from selffork_orchestrator.dashboard.body_router import build_body_router
    from selffork_orchestrator.dashboard.fleet_router import (
        FleetRegistry,
        build_fleet_router,
    )
    from selffork_orchestrator.dashboard.provider_router import (
        ProviderRegistry,
        build_provider_router,
    )

    fleet_registry = FleetRegistry()
    provider_registry = ProviderRegistry()
    body_watchdog = BodyWatchdog()
    app.state.fleet_registry = fleet_registry
    app.state.provider_registry = provider_registry
    app.state.body_watchdog = body_watchdog

    app.include_router(build_fleet_router(registry=fleet_registry))
    app.include_router(build_provider_router(registry=provider_registry))
    app.include_router(build_body_router(watchdog=body_watchdog))

    # Cockpit Settings → Vision (M5+) — operator-driven vision adapter
    # config without YAML hand-editing.
    from selffork_orchestrator.dashboard.settings_router import (
        build_settings_router,
    )

    app.include_router(build_settings_router(config_path=config.config_path))

    _register_static_mount(app, config)

    return app


# ── API routes ────────────────────────────────────────────────────────────────


def _register_api_routes(app: FastAPI, config: DashboardConfig) -> None:
    @app.get("/api/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "audit_dir": str(config.audit_dir),
            "resume_dir": str(config.resume_dir),
        }

    @app.get(
        "/api/sessions/paused",
        response_model=list[PausedSession],
    )
    async def paused() -> list[PausedSession]:
        store = ScheduledResumeStore(root=config.resume_dir)
        records = await anyio.to_thread.run_sync(store.list_all)
        now = datetime.now(UTC)
        return [
            PausedSession(
                session_id=r.session_id,
                scheduled_at=r.scheduled_at,
                resume_at=r.resume_at,
                cli_agent=r.cli_agent,
                config_path=r.config_path,
                prd_path=r.prd_path,
                workspace_path=r.workspace_path,
                reason=r.reason,
                kind=r.kind,
                is_due=r.is_due(now=now),
            )
            for r in records
        ]

    @app.get(
        "/api/sessions/recent",
        response_model=list[RecentSession],
    )
    async def recent() -> list[RecentSession]:
        def _collect() -> list[RecentSession]:
            audit_dirs: list[Path] = [config.audit_dir]
            project_store = ProjectStore(root=config.projects_root)
            for project in project_store.list_all():
                audit_dirs.append(project_store.audit_dir(project.slug))
            return list_recent_sessions(audit_dirs, limit=_RECENT_LIMIT)

        return await anyio.to_thread.run_sync(_collect)

    @app.get(
        "/api/sessions/{session_id}/events",
        response_model=list[AuditEvent],
    )
    async def events(session_id: str) -> list[AuditEvent]:
        # Resolve audit dir across orphan + project layouts. Without
        # this the recent listing surfaces a project session and the
        # detail click 404s — see Order 1 audit (#1.B).
        audit_dir = await anyio.to_thread.run_sync(
            _resolve_audit_dir, config, session_id
        )
        if audit_dir is None:
            raise HTTPException(
                status_code=404,
                detail=f"no audit log for session {session_id!r}",
            )
        # Empty audit file is rare but legal — return [] rather than 404.
        return await anyio.to_thread.run_sync(
            lambda: read_session_events(audit_dir, session_id),
        )

    @app.get(
        "/api/sessions/{session_id}/plan",
        response_model=PlanSnapshot,
    )
    async def plan(session_id: str) -> PlanSnapshot:
        record = await anyio.to_thread.run_sync(
            lambda: ScheduledResumeStore(root=config.resume_dir).load(session_id),
        )
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"no paused session for {session_id!r} — plan path lookup "
                    "currently requires a ScheduledResume record."
                ),
            )
        plan_path = Path(record.workspace_path) / ".selffork" / "plan.json"
        if not plan_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"no plan.json at {plan_path}",
            )
        try:
            data = await anyio.to_thread.run_sync(
                lambda: json.loads(plan_path.read_text(encoding="utf-8")),
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"plan.json malformed at {plan_path}: {exc}",
            ) from exc
        if not isinstance(data, dict):
            raise HTTPException(
                status_code=500,
                detail="plan.json root is not an object",
            )
        return PlanSnapshot(
            schema_version=int(data.get("schema_version", 1)),
            summary=str(data.get("summary", "")),
            sub_tasks=list(data.get("sub_tasks") or []),
        )

    @app.get(
        "/api/sessions/{session_id}/workspace",
        response_model=list[WorkspaceEntry],
    )
    async def workspace(session_id: str) -> list[WorkspaceEntry]:
        record = await anyio.to_thread.run_sync(
            lambda: ScheduledResumeStore(root=config.resume_dir).load(session_id),
        )
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"no paused session for {session_id!r} — workspace lookup "
                    "currently requires a ScheduledResume record."
                ),
            )

        def _walk_workspace() -> list[WorkspaceEntry] | None:
            root = Path(record.workspace_path)
            if not root.is_dir():
                return None
            return _list_workspace(root)

        entries = await anyio.to_thread.run_sync(_walk_workspace)
        if entries is None:
            raise HTTPException(
                status_code=404,
                detail=f"workspace directory missing at {record.workspace_path}",
            )
        return entries

    @app.post(
        "/api/sessions/run",
        response_model=RunRequestResponse,
    )
    async def run(payload: RunRequestPayload) -> RunRequestResponse:
        def _resolve_paths() -> tuple[Path, Path | None] | str:
            prd = Path(payload.prd_path).expanduser()
            if not prd.is_file():
                return f"PRD file not found: {prd}"
            cfg: Path | None = None
            if payload.config_path:
                cfg = Path(payload.config_path).expanduser()
                if not cfg.is_file():
                    return f"config file not found: {cfg}"
            return prd, cfg

        result = await anyio.to_thread.run_sync(_resolve_paths)
        if isinstance(result, str):
            raise HTTPException(status_code=400, detail=result)
        prd, cfg = result
        cmd: list[str] = [str(config.selffork_script), "run", str(prd)]
        if cfg is not None:
            cmd.extend(["--config", str(cfg)])
        # Order 1 #1.C — wire project_slug into the spawned CLI so
        # Jr's tool calls land under the right project's audit/workspace.
        # ``selffork run --project <slug>`` is already wired in cli.py:117.
        if payload.project_slug:
            cmd.extend(["--project", payload.project_slug])
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env=os.environ.copy(),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            return RunRequestResponse(
                status="failed_to_spawn",
                pid=None,
                detail=str(exc),
            )
        return RunRequestResponse(
            status="started",
            pid=proc.pid,
            detail=f"spawned `selffork run`, audit log will appear under {config.audit_dir}",
        )

    @app.post(
        "/api/sessions/paused/{session_id}/resume",
        response_model=RunRequestResponse,
    )
    async def resume_now(session_id: str) -> RunRequestResponse:
        store = ScheduledResumeStore(root=config.resume_dir)
        record = await anyio.to_thread.run_sync(
            lambda: store.load(session_id),
        )
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=f"no paused session with id {session_id!r}",
            )
        cmd: list[str] = [
            str(config.selffork_script),
            "resume",
            "now",
            session_id,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env=os.environ.copy(),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            return RunRequestResponse(
                status="failed_to_spawn",
                pid=None,
                detail=str(exc),
            )
        return RunRequestResponse(
            status="started",
            pid=proc.pid,
            detail=f"spawned `selffork resume now {session_id}`",
        )

    # ── Projects ─────────────────────────────────────────────────────────

    @app.get("/api/projects", response_model=list[ProjectResponse])
    async def list_projects() -> list[ProjectResponse]:
        store = ProjectStore(root=config.projects_root)

        def _load() -> list[ProjectResponse]:
            out: list[ProjectResponse] = []
            for project in store.list_all():
                board = store.load_board(project.slug)
                groups = board.cards_by_column()
                counts: dict[str, int] = {str(col): len(cards) for col, cards in groups.items()}
                out.append(
                    ProjectResponse(
                        slug=project.slug,
                        name=project.name,
                        description=project.description,
                        root_path=project.root_path,
                        created_at=project.created_at,
                        updated_at=project.updated_at,
                        card_counts=counts,
                    ),
                )
            return out

        return await anyio.to_thread.run_sync(_load)

    @app.post(
        "/api/projects",
        response_model=ProjectResponse,
        status_code=201,
    )
    async def create_project(payload: ProjectCreatePayload) -> ProjectResponse:
        store = ProjectStore(root=config.projects_root)

        def _create() -> ProjectResponse:
            try:
                project = store.create(
                    name=payload.name,
                    description=payload.description,
                    root_path=payload.root_path,
                )
            except ConfigError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return ProjectResponse(
                slug=project.slug,
                name=project.name,
                description=project.description,
                root_path=project.root_path,
                created_at=project.created_at,
                updated_at=project.updated_at,
                card_counts={str(col): 0 for col in DEFAULT_COLUMNS},
            )

        return await anyio.to_thread.run_sync(_create)

    @app.get(
        "/api/projects/{slug}",
        response_model=ProjectResponse,
    )
    async def get_project(slug: str) -> ProjectResponse:
        store = ProjectStore(root=config.projects_root)

        def _load() -> ProjectResponse:
            try:
                project = store.load(slug)
            except ConfigError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if project is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"project {slug!r} not found",
                )
            board = store.load_board(slug)
            groups = board.cards_by_column()
            counts: dict[str, int] = {str(col): len(cards) for col, cards in groups.items()}
            return ProjectResponse(
                slug=project.slug,
                name=project.name,
                description=project.description,
                root_path=project.root_path,
                created_at=project.created_at,
                updated_at=project.updated_at,
                card_counts=counts,
            )

        return await anyio.to_thread.run_sync(_load)

    @app.get(
        "/api/projects/{slug}/kanban",
        response_model=KanbanResponse,
    )
    async def get_kanban(slug: str) -> KanbanResponse:
        store = ProjectStore(root=config.projects_root)

        def _load() -> KanbanResponse:
            try:
                project = store.load(slug)
            except ConfigError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if project is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"project {slug!r} not found",
                )
            board = store.load_board(slug)
            return _board_to_response(board)

        return await anyio.to_thread.run_sync(_load)

    @app.post(
        "/api/projects/{slug}/kanban/cards",
        response_model=KanbanCardResponse,
        status_code=201,
    )
    async def add_kanban_card(
        slug: str,
        payload: CardCreatePayload,
    ) -> KanbanCardResponse:
        store = ProjectStore(root=config.projects_root)

        def _add() -> KanbanCardResponse:
            try:
                _validate_column(payload.column)
                card = store.add_card(
                    slug,
                    title=payload.title,
                    body=payload.body,
                    column=payload.column,  # type: ignore[arg-type]
                    order=payload.order,
                )
            except ConfigError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return _card_to_response(card)

        return await anyio.to_thread.run_sync(_add)

    @app.patch(
        "/api/projects/{slug}/kanban/cards/{card_id}/move",
        response_model=KanbanCardResponse,
    )
    async def move_kanban_card(
        slug: str,
        card_id: str,
        payload: CardMovePayload,
    ) -> KanbanCardResponse:
        store = ProjectStore(root=config.projects_root)

        def _move() -> KanbanCardResponse:
            try:
                _validate_column(payload.to_column)
                card = store.move_card(
                    slug,
                    card_id,
                    to_column=payload.to_column,  # type: ignore[arg-type]
                )
            except ConfigError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return _card_to_response(card)

        return await anyio.to_thread.run_sync(_move)

    @app.patch(
        "/api/projects/{slug}/kanban/cards/{card_id}",
        response_model=KanbanCardResponse,
    )
    async def update_kanban_card(
        slug: str,
        card_id: str,
        payload: CardUpdatePayload,
    ) -> KanbanCardResponse:
        store = ProjectStore(root=config.projects_root)

        # Pydantic v2 ``model_fields_set`` is the only way to tell
        # "user omitted this field" from "user explicitly sent null".
        # Order 1 #1.A — without it, every PATCH (even title-only)
        # silently cleared ``order`` to None, corrupting the board.
        title = (
            payload.title
            if "title" in payload.model_fields_set and payload.title is not None
            else None
        )
        body = (
            payload.body
            if "body" in payload.model_fields_set and payload.body is not None
            else None
        )
        # _SENTINEL means "key absent → leave alone". An explicit
        # ``None`` means "clear this field" — the store distinguishes.
        order: int | None | object = (
            payload.order if "order" in payload.model_fields_set else _SENTINEL
        )

        def _update() -> KanbanCardResponse:
            try:
                card = store.update_card(
                    slug,
                    card_id,
                    title=title,
                    body=body,
                    order=order,  # type: ignore[arg-type]
                )
            except ConfigError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return _card_to_response(card)

        return await anyio.to_thread.run_sync(_update)

    @app.delete(
        "/api/projects/{slug}/kanban/cards/{card_id}",
        status_code=204,
    )
    async def delete_kanban_card(slug: str, card_id: str) -> None:
        store = ProjectStore(root=config.projects_root)

        def _delete() -> None:
            try:
                removed = store.delete_card(slug, card_id)
            except ConfigError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if not removed:
                raise HTTPException(
                    status_code=404,
                    detail=f"card {card_id!r} not found in project {slug!r}",
                )

        await anyio.to_thread.run_sync(_delete)

    # ── Provider usage ──────────────────────────────────────────────────

    @app.get("/api/usage/providers", response_model=list[ProviderUsage])
    async def get_provider_usage() -> list[ProviderUsage]:
        def _aggregate() -> list[ProviderUsage]:
            audit_dirs: list[Path] = [config.audit_dir]
            # Each project contributes its own audit dir.
            store = ProjectStore(root=config.projects_root)
            for project in store.list_all():
                audit_dirs.append(store.audit_dir(project.slug))
            cfg = UsageAggregatorConfig(
                audit_dirs=tuple(audit_dirs),
                resume_store=ScheduledResumeStore(root=config.resume_dir),
            )
            return UsageAggregator(cfg).aggregate()

        return await anyio.to_thread.run_sync(_aggregate)

    # ── Mind provenance — Order 5 §8 (ChatGPT Memory Sources pattern) ─────

    @app.get(
        "/api/projects/{slug}/mind/provenance",
        response_model=list[ProvenanceEntryResponse],
    )
    async def get_project_mind_provenance(
        slug: str,
        limit: int = 100,
    ) -> list[ProvenanceEntryResponse]:
        log_path = config.projects_root / slug / "mind" / "provenance.jsonl"
        return await anyio.to_thread.run_sync(_load_provenance, log_path, limit)

    @app.get(
        "/api/mind/provenance",
        response_model=list[ProvenanceEntryResponse],
    )
    async def get_orphan_mind_provenance(
        limit: int = 100,
    ) -> list[ProvenanceEntryResponse]:
        log_path = config.audit_dir.parent / "mind" / "provenance.jsonl"
        return await anyio.to_thread.run_sync(_load_provenance, log_path, limit)

    @app.websocket("/api/sessions/{session_id}/stream")
    async def stream(websocket: WebSocket, session_id: str) -> None:
        # Resolve audit dir before accepting the WS — same multi-dir
        # logic as the events REST endpoint (Order 1 #1.B).
        audit_dir = await anyio.to_thread.run_sync(
            _resolve_audit_dir, config, session_id
        )
        if audit_dir is None:
            # Accept first so the close code reaches the client; raw
            # ``websocket.close`` before ``accept`` would 403 instead.
            await websocket.accept()
            # 4404 mirrors HTTP 404 (kanban_stream uses the same code).
            await websocket.close(
                code=4404,
                reason=f"no audit log for session {session_id}",
            )
            return
        await websocket.accept()

        # M-1 protocol — Order 2 + post-audit fix (replay registry):
        # * Monotonic ``seq`` on every envelope (audit + heartbeat) so
        #   the client can detect dropped frames.
        # * Process-level ``BoundedReplayBuffer`` keyed on the session
        #   so ``?last_seq=N`` reconnects actually resume from where the
        #   previous connection dropped (per-connection buffer was a
        #   no-op pre-fix — Order 2 audit Finding #3).
        # * 30 s heartbeat so half-open TCP is detected within one
        #   heartbeat instead of the OS socket timeout.
        last_seq = parse_last_seq(websocket.query_params.get("last_seq"))
        registry = default_registry()
        stream_key = f"audit:{session_id}"
        seq_counter = registry.counter(stream_key)
        replay_buffer = registry.buffer(stream_key)

        try:
            # Step 1 — replay anything we still have past ``last_seq``.
            # The buffer survives across connections via the registry
            # so a reconnect with ``?last_seq=N`` resumes correctly.
            for env in replay_or_gap(
                replay_buffer,
                last_seq=last_seq,
                seq_counter=seq_counter,
                session_id=session_id,
            ):
                # Replayed audit envelopes already live in the buffer;
                # only the synthetic ``gap`` frame is fresh and must be
                # appended for the next reconnect's gap math to work.
                if env.event_type == "gap":
                    replay_buffer.append(env)
                await websocket.send_text(env.model_dump_json())

            # Step 2 — heartbeat + audit tail under a single async
            # context so a leaked task can't outlive the WS.
            async with HeartbeatTask(
                websocket=websocket,
                seq_counter=seq_counter,
                session_id=session_id,
            ):
                async for ev in tail_session_events(audit_dir, session_id):
                    envelope = build_audit_envelope(
                        seq=next_seq(seq_counter),
                        payload=ev.model_dump(mode="json"),
                        session_id=session_id,
                    )
                    replay_buffer.append(envelope)
                    await websocket.send_text(envelope.model_dump_json())
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _log.exception("dashboard_ws_stream_failed", session_id=session_id)
            # Best-effort error frame — if the socket already tore down
            # the second send raises and there is nothing to recover.
            with contextlib.suppress(Exception):
                await websocket.send_text(
                    json.dumps(
                        {"error": f"{type(exc).__name__}: {exc}"},
                    ),
                )

    @app.websocket("/api/projects/{slug}/kanban/stream")
    async def kanban_stream(websocket: WebSocket, slug: str) -> None:
        await websocket.accept()
        store = ProjectStore(root=config.projects_root)
        if store.load(slug) is None:
            # Reserved app close codes start at 4000; 4404 mirrors HTTP 404
            # so the client can branch on a "project gone" cause distinctly
            # from a generic disconnect.
            await websocket.close(code=4404, reason=f"project {slug} not found")
            return
        last_serialized: str | None = None
        try:
            while True:
                board = store.load_board(slug)
                serialized = _board_to_response(board).model_dump_json()
                if serialized != last_serialized:
                    await websocket.send_text(serialized)
                    last_serialized = serialized
                await asyncio.sleep(_KANBAN_POLL_INTERVAL_SECONDS)
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _log.exception("dashboard_kanban_ws_stream_failed", slug=slug)
            await websocket.send_text(
                json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
            )


# ── Static frontend mount ─────────────────────────────────────────────────────


def _register_static_mount(app: FastAPI, config: DashboardConfig) -> None:
    """Mount the Next.js static bundle at root if available.

    During frontend dev (``npm run dev``) we keep the static_dir
    unset; the Next.js dev server runs on its own port and the
    browser hits ``http://localhost:3000`` directly. Production
    builds set static_dir to the ``out/`` directory.
    """
    if config.static_dir is None or not config.static_dir.is_dir():
        # Friendly index for dev so curl-ing http://localhost:8765/
        # shows something meaningful instead of a 404.
        @app.get("/")
        async def root_dev() -> JSONResponse:
            return JSONResponse(
                {
                    "name": "selffork dashboard",
                    "version": app.version,
                    "frontend": "not bundled — run `cd apps/web && npm run dev`",
                    "api_health": "/api/health",
                },
            )

        return

    app.mount("/", StaticFiles(directory=config.static_dir, html=True), name="static")


# ── Audit dir resolver — Order 1 ──────────────────────────────────────────────


def _resolve_audit_dir(config: DashboardConfig, session_id: str) -> Path | None:
    """Find the audit directory holding ``<session_id>.jsonl``.

    Sessions can live in two places:

    * The orphan audit dir (``config.audit_dir``) for runs without a
      project (e.g. ``selffork run prd.md`` without ``--project``).
    * Per-project audit dirs (``<projects_root>/<slug>/audit/``) for
      project-scoped runs.

    Walking both is the same pattern that ``recent`` and
    ``/api/usage/providers`` already use; the listing endpoints
    discover project sessions, so the per-session detail endpoints
    must do the same or the dashboard 404s the moment a user clicks
    a project session in the recent list.

    Returns the directory containing the file, or ``None`` if the
    session id is unknown across both layouts.
    """
    orphan_path = config.audit_dir / f"{session_id}.jsonl"
    if orphan_path.is_file():
        return config.audit_dir
    if not config.projects_root.is_dir():
        return None
    project_store = ProjectStore(root=config.projects_root)
    for project in project_store.list_all():
        candidate_dir = project_store.audit_dir(project.slug)
        if (candidate_dir / f"{session_id}.jsonl").is_file():
            return candidate_dir
    return None


# ── Workspace listing helper ──────────────────────────────────────────────────


def _list_workspace(root: Path) -> list[WorkspaceEntry]:
    """Walk ``root`` up to ``_WORKSPACE_MAX_DEPTH`` and return entries.

    Returned paths are relative to ``root`` (so the UI doesn't leak
    the user's absolute filesystem layout). Hidden files/dirs starting
    with ``.`` are kept (``.selffork/plan.json`` matters), but Python
    cache dirs (``__pycache__``, ``.mypy_cache``, ``.pytest_cache``)
    are pruned because they're noise.
    """
    out: list[WorkspaceEntry] = []
    pruned = {"__pycache__", ".mypy_cache", ".pytest_cache", "node_modules"}

    def walk(current: Path, depth: int) -> None:
        if depth > _WORKSPACE_MAX_DEPTH:
            return
        if len(out) >= _WORKSPACE_MAX_ENTRIES:
            return
        try:
            entries = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name))
        except OSError:
            return
        for entry in entries:
            if entry.name in pruned:
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            rel = str(entry.relative_to(root))
            modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            if entry.is_dir():
                out.append(
                    WorkspaceEntry(
                        path=rel,
                        kind="dir",
                        size_bytes=None,
                        modified_at=modified,
                    ),
                )
                walk(entry, depth + 1)
            else:
                out.append(
                    WorkspaceEntry(
                        path=rel,
                        kind="file",
                        size_bytes=stat.st_size,
                        modified_at=modified,
                    ),
                )
            if len(out) >= _WORKSPACE_MAX_ENTRIES:
                return

    walk(root, 0)
    return out


# ── Project / kanban helpers ─────────────────────────────────────────────────


def _card_to_response(card: KanbanCard) -> KanbanCardResponse:
    return KanbanCardResponse(
        id=card.id,
        title=card.title,
        body=card.body,
        column=card.column,
        created_at=card.created_at,
        updated_at=card.updated_at,
        completed_at=card.completed_at,
        last_touched_by_session_id=card.last_touched_by_session_id,
        order=card.order,
    )


def _board_to_response(board: KanbanBoard) -> KanbanResponse:
    """Convert a domain ``KanbanBoard`` to the wire-shape response.

    Used by both ``GET /api/projects/<slug>/kanban`` and the live
    WebSocket stream so REST and WS clients see identical payloads.
    """
    groups = board.cards_by_column()
    return KanbanResponse(
        schema_version=board.schema_version,
        columns=list(DEFAULT_COLUMNS),
        cards_by_column={
            col: [_card_to_response(c) for c in cards] for col, cards in groups.items()
        },
    )


def _validate_column(name: str) -> KanbanColumn:
    """Raise an HTTP-translatable ConfigError if ``name`` is unknown."""
    if name not in DEFAULT_COLUMNS:
        raise ConfigError(
            f"invalid column {name!r}; expected one of {list(DEFAULT_COLUMNS)}",
        )
    return name


def _load_provenance(
    log_path: Path,
    limit: int,
) -> list[ProvenanceEntryResponse]:
    """Read the project's provenance JSONL → response shape.

    Returns the most-recent ``limit`` entries (file order is append-only,
    so we slice the tail). Missing file → empty list (no error). Order
    5 §8 — ChatGPT Memory Sources pattern.
    """
    if not log_path.is_file():
        return []
    recorder = ProvenanceRecorder(log_path=log_path)
    entries = recorder.read_all()
    if limit > 0:
        entries = entries[-limit:]
    return [
        ProvenanceEntryResponse(
            ts=entry.ts,
            correlation_id=entry.correlation_id,
            session_id=entry.session_id,
            project_slug=entry.project_slug,
            query=entry.query,
            note_ids=[str(nid) for nid in entry.note_ids],
            scores=list(entry.scores),
            retriever=entry.retriever,
            reranker=entry.reranker,
        )
        for entry in entries
    ]
