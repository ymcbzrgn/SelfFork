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
from collections.abc import AsyncIterator
from collections.abc import Set as AbstractSet
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import anyio
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from selffork_mind.projections.provenance import ProvenanceRecorder

if TYPE_CHECKING:
    from selffork_orchestrator.dashboard.settings import (
        TelegramConfig,
        YamlSettingsStore,
    )
from selffork_orchestrator.dashboard.activity import (
    aggregate_activity,
    append_dashboard_activity,
    default_activity_log_path,
    default_heartbeat_audit_path,
)
from selffork_orchestrator.dashboard.audit_reader import (
    list_recent_sessions,
    read_session_events,
    tail_session_events,
)
from selffork_orchestrator.dashboard.schemas import (
    ActivityResponse,
    ActivityRow,
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
    ProjectUpdatePayload,
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
    Project,
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

# Hard cap on ``GET /api/activity?limit=`` so an always-open dashboard card
# can't request unbounded aggregation work (S8 — the Letta feed leaves its
# limit unbounded; ours is capped for a dashboard always polling).
_ACTIVITY_MAX_LIMIT = 200

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
    # Talk surface SQLite DB path (operator ↔ Self Jr conversations,
    # ADR-007 §4 S1). ``None`` falls back to
    # ``~/.selffork/talk/conversations.db``.
    talk_db_path: Path | None = None
    # Path to ``selffork.yaml``. Cockpit Settings → Vision writes the
    # ``vision:`` section back here. ``None`` disables persistent
    # updates (``POST /api/settings/vision`` returns 503).
    config_path: Path | None = None
    # S5 — Telegram bridge persistence store. ``None`` falls back to
    # ``~/.selffork/settings/telegram.yaml``. Tests can pin a
    # ``tmp_path``-rooted store so HOME mutation isn't required.
    telegram_store: object | None = None
    # S6 — CLI router stores + affinity home. ``None`` ⇒ defaults
    # (``~/.selffork/settings/*.yaml`` + ``~/.selffork`` affinity DBs).
    # Tests pin ``tmp_path``-rooted stores so HOME mutation isn't required.
    cli_override_store: object | None = None
    cli_runtime_store: object | None = None
    cli_affinity_home: Path | None = None


def build_app(config: DashboardConfig) -> FastAPI:
    """Construct the FastAPI app bound to a concrete config.

    Pure factory — no side effects on import.
    """
    # S3 Phase E: Telegram bridge + inbound application live for the
    # process lifetime. Created sync (PTB constructors don't touch
    # the network); ``initialize/start`` happens inside ``lifespan``.
    # S5 (ADR-007 §4): the resolved :class:`TelegramConfig`
    # (~/.selffork/settings/telegram.yaml > env > defaults) drives
    # all token / mode / webhook decisions on this boot.
    from selffork_orchestrator.dashboard.settings import (
        default_telegram_store,
        resolve_telegram_config,
    )
    from selffork_orchestrator.dashboard.telegram_router import (
        TelegramActivityLog,
        attach_outbound_recorder,
    )

    telegram_store = cast(
        "YamlSettingsStore[TelegramConfig]",
        config.telegram_store
        if config.telegram_store is not None
        else default_telegram_store(),
    )
    telegram_cfg = resolve_telegram_config(telegram_store)
    app_telegram_cfg = telegram_cfg
    # Stash the resolved mode so the lifespan polling-gate uses it
    # instead of an env probe (audit-god HIGH #1 fix).
    _app_telegram_mode = telegram_cfg.mode

    telegram_activity_log = TelegramActivityLog()
    outbound_bridge = _build_outbound_bridge(token=telegram_cfg.bot_token)
    wrapped_bridge = (
        attach_outbound_recorder(outbound_bridge, telegram_activity_log)
        if outbound_bridge.__class__.__name__ != "NullTelegramBridge"
        else outbound_bridge
    )

    # S-Quota Faz B — construct the CodexBar sidecar eagerly (no side
    # effects until ``lifespan`` calls ``start``). Stashed on
    # ``app.state`` so the lifespan + future provider router can both
    # reach the same instance.
    from selffork_orchestrator.snappers.codexbar_server import (
        build_default_codexbar_server,
    )
    from selffork_orchestrator.snappers.runner import (
        build_default_snapper_runner,
    )

    codexbar_server = build_default_codexbar_server()

    # S-Vision §1 BUG-1 fix — proactive snapper fleet sidecar so the
    # dashboard's quota gauges (Home, Connections) populate without a
    # manual ``selffork run`` round. Wave 2 default is **opt-out**
    # (``SELFFORK_SNAPPER_RUNNER_ENABLED=false`` disables). Returns
    # ``None`` when disabled; lifespan + teardown are then no-ops.
    snapper_runner = build_default_snapper_runner()

    # S-Auto Faz A — Heartbeat scheduler. Constructed eagerly (no side
    # effects); booted by ``lifespan`` AFTER CodexBar + Telegram so
    # the daemon sees a fully-up dependency graph. Default opt-in
    # (``SELFFORK_HEARTBEAT_ENABLED=true``); a disabled scheduler is
    # a no-op at start/stop time so the unconditional wire is safe.
    #
    # S4 F-AG #3 — wire the executor's action callables in here so
    # Heartbeat decisions actually move the world (Telegram outbound,
    # ``selffork run`` task launch, kanban card append). The
    # NullTelegramBridge is treated as "not wired" so the executor
    # surfaces a clean ``skipped`` outcome rather than silently
    # dropping messages.
    from selffork_orchestrator.cli_agent.capabilities import capability_for
    from selffork_orchestrator.dashboard.heartbeat_wire import (
        make_cli_selector,
        make_kanban_card_creator,
        make_task_starter,
    )
    from selffork_orchestrator.heartbeat.config import (
        build_default_heartbeat,
    )
    from selffork_orchestrator.router import (
        CliAffinityProvider,
        CliOverrideStore,
        CLIRouter,
        CliRuntimeStore,
        default_cli_override_store,
        default_cli_runtime_store,
        default_outcome_log_path,
    )
    from selffork_orchestrator.telegram.bridge import NullTelegramBridge
    from selffork_orchestrator.usage.codexbar_fallback import (
        build_codexbar_fallback_reader,
    )
    from selffork_orchestrator.usage.proactive import ProactiveUsageReader
    from selffork_shared.quota import QuotaSnapshot

    _telegram_for_heartbeat = (
        None
        if isinstance(wrapped_bridge, NullTelegramBridge)
        else wrapped_bridge
    )

    # S6 (ADR-006 §4.6) — CLI + model router. One quota reader (CodexBar
    # fallback over the proactive snapper) serves both the heartbeat filter
    # (per-cli) and the router's per-(cli, model) gate; ``gemini-cli`` keys
    # per model (operator 2026-05-24: gemini quota is per-model).
    # S-Vision §1 — only point the fallback reader at CodexBar HTTP
    # when a binary was actually resolved; with the sidecar disabled
    # (``SELFFORK_CODEXBAR_ENABLED=false``) the base_url would still
    # be set but the port wouldn't be served, and worse, in a test
    # environment alongside a real operator backend it would silently
    # leak into the test's data envelope.
    _quota_fallback_reader = build_codexbar_fallback_reader(
        primary=ProactiveUsageReader(),
        codexbar_base_url=(
            codexbar_server.base_url
            if codexbar_server.binary is not None
            else None
        ),
    )

    async def _per_cli_quota(cli_id: str) -> QuotaSnapshot | None:
        return await _quota_fallback_reader.read(cli_id)

    async def _model_quota(cli: str, model: str) -> QuotaSnapshot | None:
        cap = capability_for(cli)
        key = (
            f"{cli}__{model}"
            if cap is not None and cap.per_model_quota
            else cli
        )
        return await _quota_fallback_reader.read(key)

    cli_override_store = (
        cast("CliOverrideStore", config.cli_override_store)
        if config.cli_override_store is not None
        else CliOverrideStore(sticky_store=default_cli_override_store())
    )
    cli_runtime_store = (
        cast("CliRuntimeStore", config.cli_runtime_store)
        if config.cli_runtime_store is not None
        else default_cli_runtime_store()
    )
    cli_affinity_provider = CliAffinityProvider(
        home=config.cli_affinity_home,
        outcome_log_path=default_outcome_log_path(),
    )
    cli_router = CLIRouter(
        affinity=cli_affinity_provider,
        override_store=cli_override_store,
        runtime_store=cli_runtime_store,
        quota_reader=_model_quota,
    )

    _task_starter = make_task_starter(
        selffork_script=config.selffork_script,
        projects_root=config.projects_root,
        cli_router=cli_router,
    )
    _kanban_card_creator = make_kanban_card_creator(
        projects_root=config.projects_root,
    )
    heartbeat = build_default_heartbeat(
        telegram_bridge=_telegram_for_heartbeat,
        task_starter=_task_starter,
        kanban_card_creator=_kanban_card_creator,
        cli_selector=make_cli_selector(cli_router),
        quota_reader=_per_cli_quota,
        projects_root=config.projects_root,
    )
    _log.info(
        "heartbeat_callables_wired",
        extra={
            "telegram_wired": _telegram_for_heartbeat is not None,
            "task_starter_wired": True,
            "kanban_creator_wired": True,
            "cli_router_wired": True,
        },
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Late-bound — the inbound app is configured only after
        # `_register_telegram_routes` has built the InboundRouter and
        # PtbApplication and stashed them on ``app.state``.
        ptb_app = getattr(_app.state, "telegram_application", None)
        expire_task: asyncio.Task[None] | None = None
        pending_store = getattr(_app.state, "pending_confirmation_store", None)
        codexbar_server = getattr(_app.state, "codexbar_server", None)
        snapper_runner = getattr(_app.state, "snapper_runner", None)
        snapper_task: asyncio.Task[None] | None = None
        heartbeat = getattr(_app.state, "heartbeat", None)
        cli_affinity_provider = getattr(
            _app.state, "cli_affinity_provider", None
        )
        # S-Stream (ADR-011) — the Talk router spawns background generation
        # tasks via asyncio.create_task; teardown cancels any in-flight ones
        # so a shutdown doesn't orphan a streaming reply mid-token.
        talk_router_state = getattr(_app.state, "talk_router_state", None)
        # S-ToolFleet Faz 0 F4 — periodic cleanup of expired pending
        # structured questions so a long-lived dashboard process does
        # not accumulate stale dict entries.
        structured_question_store = getattr(
            _app.state, "structured_question_store", None
        )
        structured_question_cleanup_task: asyncio.Task[None] | None = None
        try:
            # S-Quota Faz B/E — boot the CodexBar sidecar first so the
            # secondary quota source is up before anything starts serving
            # HTTP. Best-effort: missing binary or boot failure logs and
            # disables the sidecar (snappers continue to carry the load).
            if codexbar_server is not None:
                try:
                    await codexbar_server.start()
                except Exception:
                    _log.exception("codexbar_sidecar_start_failed")
            # S-Vision §1 BUG-1 fix — boot the proactive snapper fleet
            # right after CodexBar so the on-disk ``cli-state/*.json``
            # surfaces start refreshing before any HTTP traffic
            # consults them. Best-effort: a startup raise logs and
            # leaves the dashboard serving (CodexBar live can carry
            # provider data until the next snapper tick lands).
            if snapper_runner is not None:
                try:
                    snapper_task = asyncio.create_task(
                        snapper_runner.serve(),
                        name="selffork.snapper_runner",
                    )
                except Exception:
                    _log.exception("snapper_runner_start_failed")
                    snapper_task = None
            if ptb_app is not None:
                # S3 audit fix #7: don't let a Telegram failure block the
                # entire dashboard. Best-effort startup; if anything
                # raises (bad token, transient network, JobQueue init),
                # disable the PTB app so teardown skips it and the rest
                # of the dashboard keeps serving HTTP.
                try:
                    await ptb_app.initialize()
                    await ptb_app.start()
                    # S5 audit-god HIGH #1 fix: the canonical mode is
                    # the one ``build_app`` resolved (YAML > env >
                    # defaults), stashed at ``app.state.telegram_mode``.
                    # Reading env here would race a YAML-only webhook
                    # config into starting both updater.poll AND a
                    # registered webhook simultaneously (Telegram
                    # rejects with 409 Conflict).
                    resolved_mode = getattr(
                        _app.state, "telegram_mode", "polling"
                    )
                    if (
                        resolved_mode != "webhook"
                        and ptb_app.updater is not None
                    ):
                        await ptb_app.updater.start_polling(
                            drop_pending_updates=True
                        )
                except Exception:
                    _log.exception("telegram_application_start_failed")
                    ptb_app = None
            if pending_store is not None:
                from selffork_orchestrator.telegram.expire_loop import (
                    expire_loop,
                )

                expire_task = asyncio.create_task(
                    expire_loop(store=pending_store, interval_seconds=60.0)
                )
            if structured_question_store is not None:
                from selffork_orchestrator.tools.structured_question import (
                    cleanup_loop as _structured_question_cleanup_loop,
                )

                structured_question_cleanup_task = asyncio.create_task(
                    _structured_question_cleanup_loop(structured_question_store),
                    name="selffork.structured_question_cleanup",
                )
            # S-Auto Faz A — Heartbeat boots last so the daemon sees a
            # fully-up dependency graph (CodexBar quota signal +
            # Telegram bridge). ``start`` is a no-op when the daemon
            # is disabled via env; any failure logs + leaves the rest
            # of the dashboard serving HTTP.
            # S6 — open the CLI-affinity DuckDB stores before the heartbeat
            # daemon (its CLI_SELECT reads them). Lazy-open is the fallback;
            # eager setup fails fast on a broken DB.
            if cli_affinity_provider is not None:
                try:
                    await cli_affinity_provider.setup()
                except Exception:
                    _log.exception("cli_affinity_provider_start_failed")
            if heartbeat is not None:
                try:
                    await heartbeat.start()
                except Exception:
                    _log.exception("heartbeat_start_failed")
            yield
        finally:
            # Talk streaming tasks first — cancel any in-flight Self Jr
            # generation so it doesn't write to a store that's about to
            # close (ADR-011). ``teardown`` is idempotent.
            if talk_router_state is not None:
                with contextlib.suppress(Exception):
                    await talk_router_state.teardown()
            # Heartbeat stops next — releases the outer loop cleanly
            # before its dependencies (Telegram outbound bridge,
            # CodexBar quota reader) tear down. ``stop`` is idempotent
            # and preserves the ``DISABLED`` terminal state.
            if heartbeat is not None:
                with contextlib.suppress(Exception):
                    await heartbeat.stop()
            # S6 — close affinity DuckDB handles after the heartbeat daemon
            # (which reads them) has stopped.
            if cli_affinity_provider is not None:
                with contextlib.suppress(Exception):
                    await cli_affinity_provider.teardown()
            if expire_task is not None:
                expire_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await expire_task
            if structured_question_cleanup_task is not None:
                structured_question_cleanup_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await structured_question_cleanup_task
            if ptb_app is not None:
                with contextlib.suppress(Exception):
                    if ptb_app.updater is not None:
                        await ptb_app.updater.stop()
                with contextlib.suppress(Exception):
                    await ptb_app.stop()
                with contextlib.suppress(Exception):
                    await ptb_app.shutdown()
            # Snapper fleet before CodexBar — runner consumers (proactive
            # reader) may already have torn down their HTTP surfaces, but
            # the snapper coroutines themselves are CPU + filesystem only
            # so cancellation is safe. ``stop()`` is anyio-Event based and
            # idempotent.
            if snapper_runner is not None and snapper_task is not None:
                snapper_runner.stop()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await snapper_task
            # CodexBar last — it has the longest tail of in-flight HTTP
            # work, and ``stop`` is idempotent on already-failed sidecars.
            if codexbar_server is not None:
                with contextlib.suppress(Exception):
                    await codexbar_server.stop()

    app = FastAPI(
        title="SelfFork Dashboard",
        version="0.1.0",
        description=(
            "Read-only views over real SelfFork artifacts on disk. "
            "ABSOLUTELY no mock data — see project_ui_stack.md."
        ),
        lifespan=lifespan,
    )
    app.state.telegram_outbound_bridge = wrapped_bridge
    app.state.telegram_mode = _app_telegram_mode
    app.state.telegram_webhook_secret = app_telegram_cfg.webhook_secret
    app.state.telegram_activity_log = telegram_activity_log
    app.state.codexbar_server = codexbar_server
    app.state.snapper_runner = snapper_runner
    app.state.quota_fallback_reader = _quota_fallback_reader
    app.state.heartbeat = heartbeat

    # S-Auto Faz G — AutonomyStore + heartbeat router. The router is
    # stateless apart from the store handle; the daemon scheduler is
    # passed for the live state endpoint.
    from selffork_orchestrator.dashboard.heartbeat_router import (
        build_heartbeat_router,
    )
    from selffork_orchestrator.dashboard.router_router import (
        build_router_router,
    )
    from selffork_orchestrator.heartbeat.autonomy import AutonomyStore

    autonomy_store = AutonomyStore.default()
    app.state.heartbeat_autonomy_store = autonomy_store
    app.include_router(
        build_heartbeat_router(store=autonomy_store, scheduler=heartbeat),
    )
    # S6 — CLI router API + state (override / affinity / capabilities /
    # config). Self Jr's CLI+model selections + the operator UI both go
    # through this router; the affinity provider is set up in ``lifespan``.
    app.state.cli_router = cli_router
    app.state.cli_affinity_provider = cli_affinity_provider
    app.include_router(build_router_router(router=cli_router))
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

    # S5 — Provider auth monitor (operator direktifi 2026-05-23:
    # "auth kendi kendine çıktıysa telegramdan uyarmamız lazım").
    # Shares the wrapped Telegram bridge so alerts land in the same
    # operator chat as destructive confirmations.
    from selffork_orchestrator.dashboard.provider_auth_monitor import (
        ProviderAuthMonitor,
    )

    provider_auth_monitor = ProviderAuthMonitor(bridge=wrapped_bridge)
    app.state.provider_auth_monitor = provider_auth_monitor

    app.include_router(build_fleet_router(registry=fleet_registry))
    app.include_router(
        build_provider_router(
            registry=provider_registry,
            auth_monitor=provider_auth_monitor,
        ),
    )
    app.include_router(build_body_router(watchdog=body_watchdog))

    # Cockpit Settings → Vision (M5+) — operator-driven vision adapter
    # config without YAML hand-editing.
    from selffork_orchestrator.dashboard.settings_router import (
        build_settings_router,
    )

    app.include_router(
        build_settings_router(
            config_path=config.config_path,
            telegram_store=telegram_store,
        ),
    )

    # M6 Live Run Theater (workspace 3-pane) + global active-loop
    # introspection (ADR-007 §4 S2). Both routers tail the shared theater
    # event DB that a separate ``selffork run`` process writes.
    from selffork_orchestrator.dashboard.theater_router import (
        build_loop_router,
        build_theater_router,
    )
    from selffork_orchestrator.theater.store import theater_db_path

    _theater_db = theater_db_path(config.projects_root)
    app.include_router(
        build_theater_router(
            projects_root=config.projects_root, db_path=_theater_db
        ),
    )
    app.include_router(build_loop_router(db_path=_theater_db))

    # M6 destructive-action soft confirmation (ADR-006 §4.5). Shared
    # store across workspaces; warden writes, dashboard reads/decides.
    from selffork_body.sandbox.pending_confirmations import (
        PendingConfirmationStore,
    )
    from selffork_orchestrator.dashboard.pending_router import (
        build_pending_router,
    )

    # Cross-process source of truth. ``selffork run`` (warden side) and
    # ``selffork ui`` (this server) must read/write the same JSONL so
    # request → approve/cancel flows survive across processes. The
    # canonical path lives under ``~/.selffork/`` (overridable via
    # ``SELFFORK_PENDING_AUDIT_PATH``) — matches ``cli._resolve_pending_audit_path``.
    pending_audit_path = Path(
        os.environ.get(
            "SELFFORK_PENDING_AUDIT_PATH",
            str(Path("~/.selffork/pending_confirmations.jsonl").expanduser()),
        )
    ).expanduser()
    pending_audit_path.parent.mkdir(parents=True, exist_ok=True)
    pending_store = PendingConfirmationStore(audit_path=pending_audit_path)
    # S3 audit fix #8: cockpit approvals/cancels must also surface in the
    # operator's Telegram chat — wire the same outbound notify hook the
    # warden process uses (see ``cli._build_pending_telegram_hook``).
    _hook = _build_dashboard_notify_hook(wrapped_bridge)
    if _hook is not None:
        pending_store.set_notify_hook(_hook)
    app.state.pending_confirmation_store = pending_store
    app.include_router(build_pending_router(store=pending_store))

    # S3 Phase E — Telegram inbound application (operator → Self Jr).
    #
    # Build the inbound router + PTB Application now (sync). The
    # ``lifespan`` context manager started above will call
    # ``initialize/start/updater.start_polling`` on it after
    # `build_app` returns. ``application`` stays ``None`` when no
    # bot token is configured — the operator simply doesn't use the
    # Telegram surface.
    _wire_telegram_inbound(
        app=app,
        pending_store=pending_store,
        talk_db_path=config.talk_db_path,
        outbound_bridge=wrapped_bridge,
        bot_token=app_telegram_cfg.bot_token,
        mode=app_telegram_cfg.mode,
        webhook_url=app_telegram_cfg.webhook_url or None,
        cli_override_store=cli_override_store,
    )

    # M6 Telegram bridge status. Reflex training surface (ADR-006 §7.1)
    # removed 2026-05-26 — fine-tune is one-shot CLI now (``selffork
    # train``); the prior dashboard form added cognitive load to a
    # daily-driver surface for a workflow the operator runs once.
    from selffork_orchestrator.dashboard.telegram_router import (
        build_telegram_router,
    )

    app.include_router(
        build_telegram_router(
            bridge=wrapped_bridge,
            application=getattr(app.state, "telegram_application", None),
            activity_log=telegram_activity_log,
            store=telegram_store,
        ),
    )
    # M6 Talk Loop — operator ↔ Self Jr conversation (ADR-007 §4 S1).
    # The Speaker model endpoint is operator-managed; S1 reads it from
    # the environment (S4 moves it to a Settings page). No endpoint set
    # ⇒ speaker=None ⇒ /send reports speaker_status='not_configured'.
    from selffork_orchestrator.dashboard.talk_router import build_talk_router
    from selffork_orchestrator.talk.speaker import SpeakerClient

    talk_endpoint = os.environ.get("SELFFORK_TALK_MODEL_ENDPOINT")
    talk_speaker = (
        SpeakerClient(
            base_url=talk_endpoint,
            model=os.environ.get("SELFFORK_TALK_MODEL", "gemma-4-e2b-it"),
        )
        if talk_endpoint
        else None
    )
    talk_router = build_talk_router(
        talk_db_path=config.talk_db_path,
        speaker=talk_speaker,
    )
    # Stash the router state so the lifespan can cancel in-flight Self Jr
    # streaming tasks on shutdown (ADR-011 S-Stream).
    app.state.talk_router_state = talk_router.state  # type: ignore[attr-defined]
    app.include_router(talk_router)

    # S3 Phase D — Telegram drafts queue surface for the Talk page banner.
    _register_drafts_routes(app)

    _register_static_mount(app, config)

    return app


_DASHBOARD_NOTIFY_TASKS: set[asyncio.Task[Any]] = set()
"""Strong refs to in-flight Telegram notify tasks scheduled from the
dashboard side (mirrors ``cli._PENDING_TELEGRAM_TASKS``)."""


def _build_dashboard_notify_hook(bridge: object) -> Any:
    """Sync :class:`NotifyHook` that schedules ``bridge.notify`` as a task.

    Cockpit approve/cancel → store mutates → ``_invoke_hook(entry, op)``
    fires → this hook builds the Telegram message and schedules
    ``bridge.notify`` on the FastAPI event loop. Same pattern as
    ``cli._build_pending_telegram_hook`` so both processes deliver
    consistent operator notifications.
    """
    from selffork_orchestrator.telegram.bridge import (
        NullTelegramBridge,
        TelegramBridge,
        TelegramMessage,
    )
    from selffork_orchestrator.telegram.destructive_notify import (
        build_message,
    )

    if isinstance(bridge, NullTelegramBridge):
        return None
    if not isinstance(bridge, TelegramBridge):
        return None

    def hook(entry: Any, op: Any) -> None:
        outbound = build_message(entry, op)
        message = TelegramMessage(
            level=outbound.level,
            text=outbound.text,
            session_id=entry.id,
            project_slug=entry.workspace_slug,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(bridge.notify(message))
        _DASHBOARD_NOTIFY_TASKS.add(task)
        task.add_done_callback(_DASHBOARD_NOTIFY_TASKS.discard)

    return hook


def _build_outbound_bridge(token: str = "") -> Any:
    """Pick a Telegram bridge based on the resolved YAML/env token.

    Lazy import keeps PTB out of the test path for non-Telegram tests
    that import :func:`build_app`. S5 (ADR-007 §4) — the resolved
    token is now passed in by ``build_app`` after consulting
    ``~/.selffork/settings/telegram.yaml``; an empty string keeps the
    bridge in :class:`NullTelegramBridge` mode (unconfigured).
    """
    from selffork_orchestrator.telegram import (
        AllowList,
        NullTelegramBridge,
        PtbTelegramBridge,
    )

    if not token:
        return NullTelegramBridge()
    allowlist = AllowList.load()
    if not allowlist.chat_ids:
        return NullTelegramBridge()
    try:
        return PtbTelegramBridge(bot_token=token, allowlist=allowlist)
    except Exception:
        return NullTelegramBridge()


def _wire_telegram_inbound(
    *,
    app: FastAPI,
    pending_store: Any,
    talk_db_path: Path | None,
    outbound_bridge: Any,
    bot_token: str = "",
    mode: str = "polling",
    webhook_url: str | None = None,
    cli_override_store: Any = None,
) -> None:
    """Construct ``InboundRouter`` + PTB ``Application`` and stash on ``app.state``.

    PTB ``Application`` only built when a bot token is configured —
    otherwise the Telegram surface is intentionally inert and the
    Connections page reports "not configured" cleanly.
    """
    from selffork_orchestrator.talk.store import TalkStore
    from selffork_orchestrator.telegram import (
        AllowList,
        InboundRouter,
        NullTelegramBridge,
        PauseSignal,
        TelegramDraftStore,
        default_drafts_path,
    )
    from selffork_orchestrator.telegram.app import (
        TelegramAppConfig,
        build_telegram_application,
    )

    drafts_store = TelegramDraftStore(path=default_drafts_path())
    app.state.telegram_drafts_store = drafts_store

    pause_signal = PauseSignal()
    app.state.telegram_pause_signal = pause_signal

    talk_store: TalkStore | None = None
    if talk_db_path is not None:
        # Surface the TalkStore so InboundRouter can resolve last_active
        # workspace + inject inbound text. ``setup()`` is async and runs
        # in ``lifespan``; stash a setup hook so the router can lazy-init.
        talk_store = TalkStore(db_path=talk_db_path)
        app.state.telegram_talk_store = talk_store

    allowlist = AllowList.load()
    # S-Bridge — voice backend resolved at boot. ``default_voice_backend``
    # returns WhisperCliVoiceBackend when the ``whisper`` binary is on
    # PATH, NullVoiceBackend otherwise; either way the InboundRouter
    # has a non-None VoiceBackend reference and operator-facing replies
    # stay friendly.
    from selffork_orchestrator.heartbeat.audit import AuditWriter
    from selffork_orchestrator.tools.structured_question import (
        build_structured_question_store,
    )
    from selffork_orchestrator.voice import default_voice_backend

    # S-Bridge CORE + S-ToolFleet Faz 0 F2 — cross-process pending
    # structured-question store. ``build_structured_question_store()``
    # picks the SQLite backend when ``SELFFORK_STRUCTURED_QUESTION_DB``
    # is set so this dashboard process and ``selffork run`` subprocesses
    # share one DB; without the env, falls back to in-memory (legacy
    # dashboard-only path — Telegram ``/answer`` only resolves
    # dashboard-spawned sessions).
    structured_question_store = build_structured_question_store()
    app.state.structured_question_store = structured_question_store

    inbound_router = InboundRouter(
        allowlist=allowlist,
        pending_store=pending_store,
        talk_store=talk_store,
        drafts_store=drafts_store,
        pause_signal=pause_signal,
        cli_override_store=cli_override_store,
        voice_backend=default_voice_backend(),
        # S-Bridge ``/correct`` command writes Correction rows next to
        # the heartbeat audit log. AuditWriter.default() resolves to the
        # canonical ``~/.selffork/audit/<latest>.jsonl`` and its
        # ``corrections.jsonl`` sibling.
        audit_writer=AuditWriter.default(),
        structured_question_store=structured_question_store,
    )
    app.state.telegram_inbound_router = inbound_router

    # Decide whether to build the PTB Application. ``NullTelegramBridge``
    # means we cannot deliver outbound, and the operator has no way to
    # send commands either — keep the inbound app off too. S5 (ADR-007
    # §4): the bot token / mode / webhook URL come from the resolved
    # :class:`TelegramConfig` (YAML > env > defaults) handed in by
    # ``build_app``; no env lookup here.
    if isinstance(outbound_bridge, NullTelegramBridge):
        app.state.telegram_application = None
        return
    if not bot_token:
        app.state.telegram_application = None
        return
    normalised_mode: Literal["polling", "webhook"] = (
        "webhook" if mode == "webhook" else "polling"
    )
    try:
        ptb_app = build_telegram_application(
            config=TelegramAppConfig(
                bot_token=bot_token,
                mode=normalised_mode,
                webhook_url=webhook_url or None,
            ),
            router=inbound_router,
        )
    except ValueError:
        app.state.telegram_application = None
        return
    app.state.telegram_application = ptb_app


async def _annotate_proactive_sources(
    app: FastAPI, rows: list[ProviderUsage]
) -> list[ProviderUsage]:
    """Tag each :class:`ProviderUsage` row with its proactive source label.

    Reads the SelfFork snapper file (sync, cheap) and falls back to
    the CodexBar sidecar (async HTTP) for every row in parallel. The
    audit-derived columns are untouched — this only writes the new
    ``proactive_source`` field.

    Tag matrix:
      * snapper file exists + CodexBar HTTP exists → ``"snapper+codexbar"``
      * only snapper file → ``"snapper"``
      * only CodexBar → ``"codexbar"``
      * neither → ``None``
    """
    from selffork_orchestrator.snappers.codexbar import (
        _SELFFORK_TO_CODEXBAR,
        CodexBarSnapper,
    )
    from selffork_orchestrator.usage.proactive import ProactiveUsageReader

    reader = ProactiveUsageReader()
    codexbar_server = getattr(app.state, "codexbar_server", None)
    base_url = (
        codexbar_server.base_url
        if codexbar_server is not None and codexbar_server.is_running
        else None
    )

    async def _probe(row: ProviderUsage) -> ProviderUsage:
        cli_id = row.cli_agent
        has_snapper = reader.read(cli_id) is not None
        has_codexbar = False
        if base_url is not None and cli_id in _SELFFORK_TO_CODEXBAR:
            snapper = CodexBarSnapper(cli_id=cli_id, base_url=base_url)
            try:
                snap = await snapper.snapshot()
                has_codexbar = snap is not None
            except Exception:
                has_codexbar = False
            finally:
                await snapper.aclose()
        label: str | None
        if has_snapper and has_codexbar:
            label = "snapper+codexbar"
        elif has_snapper:
            label = "snapper"
        elif has_codexbar:
            label = "codexbar"
        else:
            label = None
        return row.model_copy(update={"proactive_source": label})

    results = await asyncio.gather(*[_probe(row) for row in rows])
    return list(results)


def _window_label_from_seconds(seconds: int) -> str:
    """Compact human label: ``5h``, ``24h``, ``1m``, ``42s``."""
    if seconds >= 86400 and seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


async def _synthesize_proactive_rows(
    app: FastAPI, audit_cli_ids: AbstractSet[str],
) -> list[ProviderUsage]:
    """Add :class:`ProviderUsage` rows for CLIs with proactive signal only.

    S-Vision §1 BUG-1 fix — audit-derived aggregation is still the
    authoritative source. When a CLI has a quota snapshot (from the
    snapper fleet or the CodexBar sidecar) but never showed up in
    audit logs (fresh dev box, new operator), synthesize a row with
    ``calls_in_window=0`` and the snapshot's primary window so the
    dashboard's quota gauge has data to render. Audit truth wins on
    overlap; this layer only fills the no-audit-yet case.

    Requires :attr:`fastapi.FastAPI.state.quota_fallback_reader` to be
    set (built in ``build_app``); returns an empty list when missing
    (test boots that skip the dashboard's full lifespan).
    """
    from typing import cast, get_args

    from selffork_orchestrator.usage.model import ProviderName
    from selffork_shared.quota import WindowKind

    reader = getattr(app.state, "quota_fallback_reader", None)
    if reader is None:
        return []

    candidates = [
        name for name in get_args(ProviderName) if name not in audit_cli_ids
    ]

    async def _maybe_row(cli_id: str) -> ProviderUsage | None:
        try:
            snapshot = await reader.read(cli_id)
        except Exception:
            return None
        if snapshot is None or not snapshot.windows:
            return None
        window = (
            snapshot.windows.get(WindowKind.five_hour)
            or snapshot.windows.get(WindowKind.seven_day)
            or next(iter(snapshot.windows.values()))
        )
        return ProviderUsage(
            cli_agent=cast("ProviderName", cli_id),
            window_label=_window_label_from_seconds(window.window_seconds),
            window_seconds=window.window_seconds,
            calls_in_window=0,
            next_reset_at=window.resets_at,
            last_rate_limited_at=None,
        )

    results = await asyncio.gather(*[_maybe_row(c) for c in candidates])
    return [r for r in results if r is not None]


def _register_drafts_routes(app: FastAPI) -> None:
    """Talk-page drafts surface (Telegram messages with no active workspace)."""

    @app.get("/api/talk/drafts")
    async def list_drafts() -> list[dict[str, object]]:
        store = getattr(app.state, "telegram_drafts_store", None)
        if store is None:
            return []
        return [
            {
                "id": d.id,
                "sender": d.sender,
                "text": d.text,
                "received_at": d.received_at.isoformat(),
            }
            for d in store.list_unclaimed()
        ]

    @app.post("/api/talk/drafts/claim")
    async def claim_drafts(payload: dict[str, list[int]]) -> dict[str, int]:
        store = getattr(app.state, "telegram_drafts_store", None)
        if store is None:
            return {"claimed": 0}
        ids = payload.get("ids", [])
        return {"claimed": store.claim(ids)}


# ── API routes ────────────────────────────────────────────────────────────────


def _register_api_routes(app: FastAPI, config: DashboardConfig) -> None:
    @app.get("/api/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "audit_dir": str(config.audit_dir),
            "resume_dir": str(config.resume_dir),
        }

    @app.get("/api/codexbar/status")
    async def codexbar_status() -> dict[str, object]:
        """Read-only sidecar status for the Settings → CodexBar panel.

        S-Quota Wave 2 ships **read-only** — edit + auto-update toggles
        land in S4 (Settings Persistence) so we don't double-spec the
        config schema. The panel renders ``state`` as a status pill,
        ``binary`` as the resolved path (or ``null`` when disabled),
        and ``base_url`` so operators can curl it for diagnostics.
        """
        server = getattr(app.state, "codexbar_server", None)
        if server is None:
            return {
                "state": "disabled",
                "binary": None,
                "base_url": None,
                "port": None,
                "fail_reason": None,
            }
        return {
            "state": server.state.value,
            "binary": str(server.binary) if server.binary else None,
            "base_url": server.base_url,
            "port": server.port,
            "fail_reason": server.fail_reason,
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

    @app.get("/api/activity", response_model=ActivityResponse)
    async def activity(
        limit: int = 50,
        since: datetime | None = None,
        before: datetime | None = None,
        project_slug: str | None = None,
        event_kind: str | None = None,
    ) -> ActivityResponse:
        """Aggregate recent activity across all four CLIs' sessions, the
        heartbeat tick log, project mutations, and the Telegram bridge —
        ADR-007 §4 S8.

        No-mock: every row derives from a real audit/activity artifact, so
        an idle system returns an empty feed. ``limit`` is capped server-
        side (Letta's feed leaves its limit unbounded; a dashboard card
        polling every 10 s must not be able to request unbounded work).
        ``since`` / ``before`` bound the ts window; ``project_slug`` /
        ``event_kind`` filter the merged rows.
        """
        capped = max(1, min(limit, _ACTIVITY_MAX_LIMIT))
        telegram_log = getattr(app.state, "telegram_activity_log", None)
        telegram_snapshot = (
            telegram_log.snapshot() if telegram_log is not None else None
        )

        def _aggregate() -> tuple[list[ActivityRow], bool]:
            return aggregate_activity(
                audit_dir=config.audit_dir,
                projects_root=config.projects_root,
                heartbeat_audit_path=default_heartbeat_audit_path(config.audit_dir),
                activity_log_path=default_activity_log_path(config.audit_dir),
                telegram_activity=telegram_snapshot,
                limit=capped,
                since=since,
                before=before,
                project_slug=project_slug,
                event_kind=event_kind,
            )

        rows, has_more = await anyio.to_thread.run_sync(_aggregate)
        return ActivityResponse(rows=rows, has_more=has_more)

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
    async def list_projects(
        include_archived: bool = False,
    ) -> list[ProjectResponse]:
        store = ProjectStore(root=config.projects_root)

        def _load() -> list[ProjectResponse]:
            out: list[ProjectResponse] = []
            for project in store.list_all():
                if not include_archived and project.archived_at is not None:
                    continue
                out.append(
                    _project_to_response(project, _counts_for(store, project.slug)),
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
            return _project_to_response(
                project,
                {str(col): 0 for col in DEFAULT_COLUMNS},
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
            return _project_to_response(project, _counts_for(store, slug))

        return await anyio.to_thread.run_sync(_load)

    # ── Projects: edit / archive / autopilot pause (S7 — ADR-007 §4) ────

    @app.put(
        "/api/projects/{slug}",
        response_model=ProjectResponse,
    )
    async def update_project(
        slug: str,
        payload: ProjectUpdatePayload,
    ) -> ProjectResponse:
        store = ProjectStore(root=config.projects_root)

        def _update() -> ProjectResponse:
            # ``root_path`` arrives as ``None`` for "omitted, leave
            # alone"; per ``ProjectUpdatePayload`` docstring, callers
            # send ``""`` to explicitly clear. Two branches keep mypy
            # happy without needing to leak ``_Sentinel`` into the
            # endpoint surface.
            try:
                if payload.root_path is None:
                    project = store.update_meta(
                        slug,
                        name=payload.name,
                        description=payload.description,
                    )
                else:
                    project = store.update_meta(
                        slug,
                        name=payload.name,
                        description=payload.description,
                        root_path=payload.root_path or None,
                    )
            except ConfigError as exc:
                if "not found" in str(exc):
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return _project_to_response(project, _counts_for(store, slug))

        return await anyio.to_thread.run_sync(_update)

    @app.post(
        "/api/projects/{slug}/archive",
        response_model=ProjectResponse,
    )
    async def archive_project(slug: str) -> ProjectResponse:
        """Soft-archive — set ``archived_at`` to now. Reversible via
        :func:`unarchive_project`. Idempotent (repeat refreshes the
        timestamp)."""
        store = ProjectStore(root=config.projects_root)

        def _archive() -> ProjectResponse:
            try:
                project = store.update_meta(
                    slug,
                    archived_at=datetime.now(UTC),
                )
            except ConfigError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            with contextlib.suppress(OSError):
                append_dashboard_activity(
                    default_activity_log_path(config.audit_dir),
                    category="project_archived",
                    summary=f"Workspace '{project.name}' archived",
                    project_slug=slug,
                    payload={"name": project.name},
                )
            return _project_to_response(project, _counts_for(store, slug))

        return await anyio.to_thread.run_sync(_archive)

    @app.post(
        "/api/projects/{slug}/unarchive",
        response_model=ProjectResponse,
    )
    async def unarchive_project(slug: str) -> ProjectResponse:
        """Clear ``archived_at`` — project re-enters the sidebar listing
        and becomes Heartbeat-eligible again."""
        store = ProjectStore(root=config.projects_root)

        def _unarchive() -> ProjectResponse:
            try:
                project = store.update_meta(slug, archived_at=None)
            except ConfigError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            with contextlib.suppress(OSError):
                append_dashboard_activity(
                    default_activity_log_path(config.audit_dir),
                    category="project_unarchived",
                    summary=f"Workspace '{project.name}' unarchived",
                    project_slug=slug,
                    payload={"name": project.name},
                )
            return _project_to_response(project, _counts_for(store, slug))

        return await anyio.to_thread.run_sync(_unarchive)

    @app.post(
        "/api/projects/{slug}/autopilot/pause",
        response_model=ProjectResponse,
    )
    async def pause_workspace_autopilot(slug: str) -> ProjectResponse:
        """Workspace-scope Self Jr pause.

        Sets ``autopilot_paused=True``. Heartbeat's
        :class:`WorldStateBuilder` consults the flag on subsequent ticks
        (``config.py`` wires the eligibility probe from
        :class:`ProjectStore`) — an in-flight session completes its
        current round, then no new round starts for this workspace
        until :func:`resume_workspace_autopilot` is called. Idempotent.

        Note: hard interrupt of an already-running session is deferred.
        ``selffork run`` (the dashboard's spawn path) runs the CLI as
        an awaited asyncio subprocess, not under tmux, and the
        dashboard currently has no pid registry keyed by
        ``workspace_slug``. Audit-god S7 Finding #1 (2026-05-24) caught
        a tmux-kill implementation that targeted a session name no
        producer creates; that code was removed pending a proper
        ``RunningSessionRegistry`` (follow-up sprint). The flag-driven
        pause is the durable primitive; immediate interrupt arrives
        with the registry.
        """
        store = ProjectStore(root=config.projects_root)

        def _pause() -> ProjectResponse:
            try:
                project = store.update_meta(slug, autopilot_paused=True)
            except ConfigError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            with contextlib.suppress(OSError):
                append_dashboard_activity(
                    default_activity_log_path(config.audit_dir),
                    category="project_paused",
                    summary=f"Self Jr paused for workspace '{project.name}'",
                    project_slug=slug,
                    payload={"name": project.name},
                )
            return _project_to_response(project, _counts_for(store, slug))

        return await anyio.to_thread.run_sync(_pause)

    @app.post(
        "/api/projects/{slug}/autopilot/resume",
        response_model=ProjectResponse,
    )
    async def resume_workspace_autopilot(slug: str) -> ProjectResponse:
        """Clear ``autopilot_paused``. Heartbeat is eligible to pick this
        workspace on its next tick."""
        store = ProjectStore(root=config.projects_root)

        def _resume() -> ProjectResponse:
            try:
                project = store.update_meta(slug, autopilot_paused=False)
            except ConfigError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            with contextlib.suppress(OSError):
                append_dashboard_activity(
                    default_activity_log_path(config.audit_dir),
                    category="project_resumed",
                    summary=f"Self Jr resumed for workspace '{project.name}'",
                    project_slug=slug,
                    payload={"name": project.name},
                )
            return _project_to_response(project, _counts_for(store, slug))

        return await anyio.to_thread.run_sync(_resume)

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

        rows = await anyio.to_thread.run_sync(_aggregate)
        # S-Vision §1 BUG-1 — synthesize rows for CLIs with proactive
        # signal but no audit history yet (snapper or CodexBar
        # sidecar). The dashboard gauge needs data to render on a
        # fresh dev box; audit truth still wins on overlap.
        audit_cli_ids = {row.cli_agent for row in rows}
        synthesized = await _synthesize_proactive_rows(app, audit_cli_ids)
        # S-Quota Wave 2 — enrich each row with a proactive_source tag
        # ("snapper" / "codexbar" / "snapper+codexbar" / None) so the
        # Connections card can show where the secondary data comes
        # from without conflating it with the audit-derived columns.
        return await _annotate_proactive_sources(app, rows + synthesized)

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


def _counts_for(store: ProjectStore, slug: str) -> dict[str, int]:
    """Kanban card counts per column for one project."""
    board = store.load_board(slug)
    groups = board.cards_by_column()
    return {str(col): len(cards) for col, cards in groups.items()}


def _project_to_response(
    project: Project,
    counts: dict[str, int],
) -> ProjectResponse:
    """Lift a stored :class:`Project` into its wire shape (S7 — adds
    ``archived_at`` + ``autopilot_paused`` to the canonical row)."""
    return ProjectResponse(
        slug=project.slug,
        name=project.name,
        description=project.description,
        root_path=project.root_path,
        created_at=project.created_at,
        updated_at=project.updated_at,
        card_counts=counts,
        archived_at=project.archived_at,
        autopilot_paused=project.autopilot_paused,
    )


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
