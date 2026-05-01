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
    RecentSession,
    RunRequestPayload,
    RunRequestResponse,
    WorkspaceEntry,
)
from selffork_orchestrator.projects.model import (
    DEFAULT_COLUMNS,
    KanbanCard,
    KanbanColumn,
)
from selffork_orchestrator.projects.store import ProjectStore
from selffork_orchestrator.resume.store import ScheduledResumeStore
from selffork_orchestrator.usage.aggregator import (
    UsageAggregator,
    UsageAggregatorConfig,
)
from selffork_orchestrator.usage.model import ProviderUsage
from selffork_shared.errors import ConfigError
from selffork_shared.logging import get_logger

__all__ = ["DashboardConfig", "build_app"]

_log = get_logger(__name__)

# Number of recent sessions returned by ``GET /api/sessions/recent``.
# 50 is enough for a dashboard list without paginating.
_RECENT_LIMIT = 50

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
        return await anyio.to_thread.run_sync(
            lambda: list_recent_sessions(config.audit_dir, limit=_RECENT_LIMIT),
        )

    @app.get(
        "/api/sessions/{session_id}/events",
        response_model=list[AuditEvent],
    )
    async def events(session_id: str) -> list[AuditEvent]:
        evs = await anyio.to_thread.run_sync(
            lambda: read_session_events(config.audit_dir, session_id),
        )
        if not evs:
            # Distinguish "session never existed" from "empty file"
            # by checking the file. An empty audit file is rare but
            # legal — return [] rather than 404.
            audit_path = config.audit_dir / f"{session_id}.jsonl"
            if not audit_path.is_file():
                raise HTTPException(
                    status_code=404,
                    detail=f"no audit log for session {session_id!r}",
                )
        return evs

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
            groups = board.cards_by_column()
            return KanbanResponse(
                schema_version=board.schema_version,
                columns=list(DEFAULT_COLUMNS),
                cards_by_column={
                    col: [_card_to_response(c) for c in cards] for col, cards in groups.items()
                },
            )

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

        def _update() -> KanbanCardResponse:
            try:
                card = store.update_card(
                    slug,
                    card_id,
                    title=payload.title,
                    body=payload.body,
                    order=payload.order if payload.order is not None else None,
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

    @app.websocket("/api/sessions/{session_id}/stream")
    async def stream(websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        try:
            async for ev in tail_session_events(config.audit_dir, session_id):
                # Pydantic JSON serialization handles datetime/UTC for us.
                await websocket.send_text(ev.model_dump_json())
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _log.exception("dashboard_ws_stream_failed", session_id=session_id)
            await websocket.send_text(
                json.dumps(
                    {"error": f"{type(exc).__name__}: {exc}"},
                ),
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


def _validate_column(name: str) -> KanbanColumn:
    """Raise an HTTP-translatable ConfigError if ``name`` is unknown."""
    if name not in DEFAULT_COLUMNS:
        raise ConfigError(
            f"invalid column {name!r}; expected one of {list(DEFAULT_COLUMNS)}",
        )
    return name
