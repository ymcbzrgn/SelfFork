"""``selffork`` user-facing CLI.

Single subcommand: ``selffork run <prd-path>``. Wires every collaborator
(runtime, sandbox, CLI agent, plan store, audit logger) and drives one
:class:`Session` end-to-end. Exits ``0`` on COMPLETED, ``1`` on FAILED,
``2`` on usage / config errors before the session even starts.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §17 step 8.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from selffork_body.sandbox.destructive_whitelist import DestructiveWhitelist
from selffork_body.sandbox.pending_confirmations import (
    PendingConfirmationStore,
)
from selffork_orchestrator import __version__
from selffork_orchestrator.cli_agent.factory import build_cli_agent
from selffork_orchestrator.cli_mind import mind_app
from selffork_orchestrator.lifecycle.session import Session
from selffork_orchestrator.lifecycle.states import SessionState
from selffork_orchestrator.lifecycle.stuck_detector import StuckDetector
from selffork_orchestrator.limits.base import RateLimited
from selffork_orchestrator.limits.factory import build_limit_detector
from selffork_orchestrator.plan.factory import build_plan_store
from selffork_orchestrator.resume.cron import (
    LaunchdScheduler,
    LaunchdSchedulerError,
    is_macos,
)
from selffork_orchestrator.resume.store import ScheduledResume, ScheduledResumeStore
from selffork_orchestrator.router import (
    CliOverrideStore,
    default_cli_override_store,
    default_cli_runtime_store,
)
from selffork_orchestrator.runtime.factory import build_runtime
from selffork_orchestrator.runtime.mlx_server import MlxServerRuntime
from selffork_orchestrator.sandbox.factory import build_sandbox
from selffork_orchestrator.spawn.runner import SpawnRunnerConfig, TmuxSpawnRunner
from selffork_orchestrator.theater.producer import (
    NullTheaterProducer,
    StoreTheaterProducer,
    TheaterProducer,
)
from selffork_orchestrator.theater.store import TheaterStore, theater_db_path
from selffork_orchestrator.tmux.factory import build_tmux_driver
from selffork_orchestrator.tools.structured_question import (
    PendingStructuredQuestionStore,
    SqlitePendingStructuredQuestionStore,
)
from selffork_shared.audit import AuditLogger
from selffork_shared.config import SelfForkSettings, load_settings
from selffork_shared.errors import ConfigError, SelfForkError
from selffork_shared.logging import bind_correlation_id, bind_session_id, get_logger, setup_logging
from selffork_shared.ulid import new_ulid

# Default location of scheduled-resume records. Each paused session is
# one JSON file under here. Override via ``SELFFORK_RESUME_DIR`` env var.
_DEFAULT_RESUME_DIR = Path("~/.selffork/scheduled").expanduser()
_DEFAULT_PROJECTS_ROOT = Path("~/.selffork/projects").expanduser()
_DEFAULT_PENDING_AUDIT_PATH = Path("~/.selffork/pending_confirmations.jsonl").expanduser()

# Strong references to in-flight Telegram notify tasks so they don't get
# garbage-collected mid-await. The callback in :func:`_build_pending_telegram_hook`
# removes finished tasks; the set stays tiny under normal load.
_PENDING_TELEGRAM_TASKS: set[asyncio.Task[Any]] = set()

__all__ = ["app"]

_log = get_logger(__name__)

app = typer.Typer(
    name="selffork",
    help="Autonomous coding orchestrator — non-fine-tuned local Gemma + opencode.",
    no_args_is_help=True,
    rich_markup_mode=None,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"selffork {__version__}")
        raise typer.Exit


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show SelfFork version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """SelfFork — orchestrator pillar entrypoint."""


@app.command()
def run(
    prd: Annotated[
        Path,
        typer.Argument(
            ...,
            help="Path to a PRD (Product Requirements Document) — Markdown or plain text.",
            exists=False,  # we validate explicitly to give a clearer error
        ),
    ],
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="Path to a selffork.yaml. Defaults to ./selffork.yaml or ./selffork.yml.",
        ),
    ] = None,
    mode: Annotated[
        str | None,
        typer.Option(
            "--mode",
            help="Override sandbox mode: 'subprocess' (Mac dev) or 'docker' (server).",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help=(
                "Run inside the named project — Jr's tool calls "
                "(kanban_*) will read+write that project's board. "
                "Per project_run_project_routing_followup.md, audit + "
                "sandbox dirs stay global for now; tooling is wired."
            ),
        ),
    ] = None,
    cli: Annotated[
        str | None,
        typer.Option(
            "--cli",
            help=(
                "Override the CLI agent for this run "
                "(claude-code/codex/gemini-cli/opencode/minimax-cli). "
                "The S6 router passes the selected CLI here."
            ),
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="Override the CLI's model for this run (S6 in-CLI routing).",
        ),
    ] = None,
    effort: Annotated[
        str | None,
        typer.Option(
            "--effort",
            help="Override the CLI's reasoning effort for this run (S6).",
        ),
    ] = None,
) -> None:
    """Run a PRD end-to-end via opencode + the configured local LLM runtime."""
    try:
        settings = load_settings(config)
    except ConfigError as exc:
        typer.echo(f"selffork: configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if mode is not None:
        if mode not in {"subprocess", "docker"}:
            typer.echo(
                f"selffork: --mode must be 'subprocess' or 'docker', got {mode!r}",
                err=True,
            )
            raise typer.Exit(code=2)
        settings = settings.model_copy(
            update={"sandbox": settings.sandbox.model_copy(update={"mode": mode})},
        )

    # S6 (ADR-006 §4.6): the router selects cli + model + effort and passes
    # them here; they override the static ``cli_agent`` config so the
    # CLIAgent applies the chosen model/effort via its capability.
    if cli is not None or model is not None or effort is not None:
        cli_update: dict[str, object] = {}
        if cli is not None:
            cli_update["agent"] = cli
        if model is not None:
            cli_update["model"] = model
        if effort is not None:
            cli_update["effort"] = effort
        settings = settings.model_copy(
            update={"cli_agent": settings.cli_agent.model_copy(update=cli_update)},
        )

    setup_logging(settings.logging)

    if not prd.is_file():
        typer.echo(f"selffork: PRD file not found: {prd}", err=True)
        raise typer.Exit(code=2)
    prd_text = prd.read_text(encoding="utf-8")

    session_id = new_ulid()
    bind_correlation_id()
    bind_session_id(session_id)
    _log.info("cli_run_start", session_id=session_id, prd=str(prd), mode=settings.sandbox.mode)

    resume_dir = _resolve_resume_dir()
    spawn_log_root = Path(settings.logging.log_dir).expanduser() / "spawned"
    projects_root = _resolve_projects_root()

    # Validate the project slug up-front so we fail fast (the dashboard
    # and the user both need predictable feedback when a typo'd slug
    # comes in via --project or POST /api/sessions/run).
    if project is not None:
        from selffork_orchestrator.projects.store import ProjectStore

        if ProjectStore(root=projects_root).load(project) is None:
            typer.echo(
                f"selffork: project {project!r} not found under {projects_root}",
                err=True,
            )
            raise typer.Exit(code=2)

    try:
        outcome, failure_reason = asyncio.run(
            _amain(
                settings,
                prd,
                prd_text,
                session_id,
                config_path=config,
                resume_dir=resume_dir,
                spawn_log_root=spawn_log_root,
                projects_root=projects_root,
                project_slug=project,
            ),
        )
    except SelfForkError as exc:
        typer.echo(f"selffork: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if outcome == SessionState.COMPLETED:
        typer.echo(f"selffork: session {session_id} completed successfully.")
        raise typer.Exit(code=0)
    if outcome == SessionState.PAUSED_RATE_LIMIT:
        typer.echo(
            f"selffork: session {session_id} paused (rate limit). "
            f"Run `selffork resume watch` (or `selffork resume now {session_id}`).",
        )
        # Exit code 75 (EX_TEMPFAIL) — POSIX "transient failure, try again later".
        # Distinct from auth/config (2) and hard failure (1) so cron-style
        # retry wrappers can react specifically.
        raise typer.Exit(code=75)
    typer.echo(
        f"selffork: session {session_id} failed: {failure_reason or 'unknown reason'}",
        err=True,
    )
    raise typer.Exit(code=1)


@app.command(name="run-many")
def run_many(
    prds: Annotated[
        list[Path],
        typer.Argument(
            ...,
            help="Two or more PRD paths to run in parallel tmux panes.",
        ),
    ],
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="Path to a selffork.yaml. Defaults to ./selffork.yaml or ./selffork.yml.",
        ),
    ] = None,
    detach: Annotated[
        bool,
        typer.Option(
            "--detach",
            help=(
                "Spawn the panes and exit immediately. Without this, the "
                "orchestrator polls panes until all finish and prints an "
                "aggregate report."
            ),
        ),
    ] = False,
) -> None:
    """Run N PRDs in parallel against a single shared MLX runtime.

    Each PRD runs in its own tmux pane with an independent SelfFork-Jr
    round-loop and an independent CLI agent process; they all share one
    MLX server (spawned by this parent process) so the model loads once.
    """
    try:
        settings = load_settings(config)
    except ConfigError as exc:
        typer.echo(f"selffork: configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    setup_logging(settings.logging)

    if settings.runtime.mode != "owned":
        typer.echo(
            "selffork: run-many requires runtime.mode='owned' so the parent "
            f"can spawn the shared MLX server. Got mode={settings.runtime.mode!r}.",
            err=True,
        )
        raise typer.Exit(code=2)

    if len(prds) < 2:
        typer.echo(
            "selffork: run-many needs at least two PRDs (use 'selffork run' for one).",
            err=True,
        )
        raise typer.Exit(code=2)

    for prd in prds:
        if not prd.is_file():
            typer.echo(f"selffork: PRD file not found: {prd}", err=True)
            raise typer.Exit(code=2)

    session_id = new_ulid()
    bind_correlation_id()
    bind_session_id(session_id)
    _log.info("cli_run_many_start", session_id=session_id, prd_count=len(prds))

    log_root = Path(settings.logging.log_dir).expanduser() / f"run-many-{session_id}"
    log_root.mkdir(parents=True, exist_ok=True)

    try:
        results = asyncio.run(
            _amain_run_many(
                settings,
                prds,
                config,
                session_id,
                log_root=log_root,
                detach=detach,
            ),
        )
    except SelfForkError as exc:
        typer.echo(f"selffork: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if detach:
        raise typer.Exit(code=0)

    success = all(c == 0 for c in results.values())
    raise typer.Exit(code=0 if success else 1)


async def _amain_run_many(
    settings: SelfForkSettings,
    prds: list[Path],
    config_path: Path | None,
    session_id: str,
    *,
    log_root: Path,
    detach: bool,
) -> dict[int, int | None]:
    """Async orchestrator for ``run-many``.

    Returns a ``{pane_index: exit_code | None}`` mapping when running
    attached; an empty dict when ``detach=True``.
    """
    runtime = MlxServerRuntime(settings.runtime)
    tmux = build_tmux_driver()

    # tmux session names must be filesystem-safe and short. Use the last
    # 12 chars of the ULID, lowercased.
    tmux_session_name = f"selffork-{session_id[-12:].lower()}"
    panes: list[tuple[int, str, Path]] = []

    try:
        await runtime.start()
        actual_port = runtime.actual_port
        if actual_port is None:
            raise SelfForkError("MLX runtime started but actual_port is None")

        await tmux.create_session(name=tmux_session_name)

        selffork_script = Path(sys.executable).parent / "selffork"

        for i, prd in enumerate(prds):
            pane_log = log_root / f"pane-{i:02d}.log"
            cmd = _build_child_command(
                selffork_script=selffork_script,
                prd=prd,
                config_path=config_path,
                shared_host=settings.runtime.host,
                shared_port=actual_port,
            )
            pane_id = await tmux.add_pane(
                session_id=tmux_session_name,
                command=cmd,
                log_path=pane_log,
            )
            panes.append((i, pane_id, pane_log))
            _log.info(
                "run_many_pane_spawned",
                pane_index=i,
                pane_id=pane_id,
                prd=str(prd),
                log=str(pane_log),
            )

        attach_hint = f"tmux attach -t {tmux_session_name}"
        typer.echo(
            f"selffork: spawned {len(prds)} panes in tmux session "
            f"{tmux_session_name!r} sharing MLX server on port {actual_port}.",
        )
        typer.echo(f"selffork: watch live with: {attach_hint}")
        typer.echo(f"selffork: per-pane logs: {log_root}")

        if detach:
            return {}

        # Poll until every pane is dead. 2s interval is cheap enough; tmux
        # panes don't change state mid-poll without a tmux event.
        while True:
            still_alive: list[int] = []
            for i, pid, _ in panes:
                if await tmux.is_pane_alive(pane_id=pid):
                    still_alive.append(i)
            if not still_alive:
                break
            _log.info("run_many_poll", alive_panes=still_alive)
            await asyncio.sleep(2.0)

        results: dict[int, int | None] = {}
        for i, _, log_path in panes:
            results[i] = _parse_exit_code(log_path)

        # Human-readable summary.
        for i in sorted(results):
            code = results[i]
            status = "OK" if code == 0 else f"FAILED (exit {code})"
            typer.echo(f"  pane-{i:02d} → {status}  (log: {log_root / f'pane-{i:02d}.log'})")

        return results
    finally:
        # Detached runs leave the tmux session so the user can attach
        # later; attached runs always tear down.
        if not detach:
            await tmux.kill_session(session_id=tmux_session_name)
        await runtime.stop()


def _build_child_command(
    *,
    selffork_script: Path,
    prd: Path,
    config_path: Path | None,
    shared_host: str,
    shared_port: int,
) -> str:
    """Build the shell command sent to a tmux pane for one child run.

    Inline env vars switch the child runtime to shared mode pointing at
    the parent's MLX server. The trailing ``echo "[SELFFORK:EXIT:$?]"``
    is the sentinel pattern the parent reads from per-pane logs to
    aggregate exit codes (tmux has no native exit-code API). Works in
    bash and zsh; the user's default shell on macOS.
    """
    parts: list[str] = [
        "SELFFORK_RUNTIME__MODE=shared",
        f"SELFFORK_RUNTIME__PORT={shared_port}",
        f"SELFFORK_RUNTIME__HOST={shlex.quote(shared_host)}",
        shlex.quote(str(selffork_script)),
        "run",
        shlex.quote(str(prd)),
    ]
    if config_path is not None:
        parts.append("--config")
        parts.append(shlex.quote(str(config_path)))
    base = " ".join(parts)
    return f'{base}; echo "[SELFFORK:EXIT:$?]"'


_EXIT_RE = re.compile(r"\[SELFFORK:EXIT:(-?\d+)\]")


def _parse_exit_code(log_path: Path) -> int | None:
    """Return the last ``[SELFFORK:EXIT:<n>]`` exit code from ``log_path``.

    Returns ``None`` if the sentinel never appeared (pane killed early,
    log not yet flushed, etc.).
    """
    if not log_path.is_file():
        return None
    text = log_path.read_text(encoding="utf-8", errors="replace")
    matches = _EXIT_RE.findall(text)
    if not matches:
        return None
    return int(matches[-1])


async def _amain(
    settings: SelfForkSettings,
    prd_path: Path,
    prd_text: str,
    session_id: str,
    *,
    config_path: Path | None,
    resume_dir: Path,
    spawn_log_root: Path,
    projects_root: Path,
    project_slug: str | None,
) -> tuple[SessionState, str | None]:
    """Async orchestrator. Returns (outcome, failure_reason)."""
    settings = _apply_project_routing(
        settings,
        project_slug=project_slug,
        projects_root=projects_root,
    )
    audit_logger = AuditLogger(settings.audit, session_id=session_id)
    runtime = build_runtime(settings.runtime)
    sandbox = build_sandbox(settings.sandbox, session_id=session_id)
    cli_agent = build_cli_agent(settings.cli_agent)
    limit_detector = build_limit_detector(settings.cli_agent.agent)
    resume_store = ScheduledResumeStore(root=resume_dir)

    # Pre-spawn the sandbox so we can build the plan store with a concrete
    # workspace path. ``Session._prepare`` will call ``spawn()`` again —
    # both ``SubprocessSandbox`` and ``DockerSandbox`` are idempotent on
    # repeated spawn.
    await sandbox.spawn()
    # Pre-start the runtime too so we know its port for the SpawnRunner
    # config (children attach in shared mode). Session._prepare will call
    # start() again; MlxServerRuntime.start() is idempotent on the
    # already-started case.
    await runtime.start()

    plan_store = build_plan_store(
        settings.plan,
        workspace_path=sandbox.host_workspace_path,
    )
    plan_path_in_sandbox = str(Path(sandbox.workspace_path) / settings.plan.plan_filename)

    workspace_path_str = sandbox.host_workspace_path

    # SPAWN handler — used when parent Jr emits ``[SELFFORK:SPAWN: ...]``.
    # Only available when the runtime exposes a concrete port (mlx-server
    # in owned mode); other backends will land in M2-M3.
    spawn_handler: TmuxSpawnRunner | None = None
    if isinstance(runtime, MlxServerRuntime) and runtime.actual_port is not None:
        spawn_handler = TmuxSpawnRunner(
            tmux=build_tmux_driver(),
            config=SpawnRunnerConfig(
                selffork_script=Path(sys.executable).parent / "selffork",
                config_path=config_path,
                shared_host=settings.runtime.host,
                shared_port=runtime.actual_port,
                log_root=spawn_log_root,
            ),
        )

    async def _persist_paused_session(
        *,
        session_id: str,
        verdict: RateLimited,
        last_round_text: str,
    ) -> None:
        record = ScheduledResume(
            session_id=session_id,
            scheduled_at=datetime.now(UTC),
            resume_at=verdict.reset_at,
            cli_agent=settings.cli_agent.agent,
            config_path=str(config_path) if config_path is not None else None,
            prd_path=str(prd_path),
            workspace_path=workspace_path_str,
            reason=verdict.reason,
            kind=verdict.kind,
        )
        resume_store.save(record)
        # Stash the last operator-style message we sent the CLI agent so
        # ``selffork resume`` can splice it back in when the window opens.
        # We piggyback on the same JSON file by storing it as a sibling
        # field — done via a second save with a wider record. Keep simple
        # for MVP: append to a dedicated .last_round_text file next to it.
        last_round_path = resume_dir / f"{session_id}.last_round.txt"
        last_round_path.parent.mkdir(parents=True, exist_ok=True)
        last_round_path.write_text(last_round_text, encoding="utf-8")

    # Wire the tool registry + project context. When --project was
    # passed, Jr's kanban_* tools target that project's board; without
    # it, the registry is still attached but tool calls return
    # ``unauthorized`` results (Jr learns it can't kanban an orphan run).
    import anyio

    from selffork_orchestrator.projects.store import ProjectStore as _ProjectStore
    from selffork_orchestrator.snappers import (
        SnapperRunner,
        SnapperRunnerConfig,
        build_default_snappers,
    )
    from selffork_orchestrator.tools import build_default_registry
    from selffork_orchestrator.usage.proactive import ProactiveUsageReader

    tool_registry = build_default_registry()
    project_store_for_tools: _ProjectStore | None = None
    if project_slug is not None:
        project_store_for_tools = _ProjectStore(root=projects_root)

    # Theater producer — surfaces the round-loop in the Workspace Live
    # Run theater (ADR-007 §4 S2). Project runs only: an orphan run has
    # no workspace to attach a theater to, so it gets the Null producer.
    theater_store: TheaterStore | None = None
    theater_producer: TheaterProducer = NullTheaterProducer()
    if project_slug is not None and project_store_for_tools is not None:
        project = project_store_for_tools.load(project_slug)
        if project is not None:
            theater_store = TheaterStore(
                db_path=theater_db_path(projects_root),
            )
            await theater_store.setup()
            theater_producer = StoreTheaterProducer(
                store=theater_store,
                session_id=session_id,
                workspace_slug=project_slug,
                workspace_name=project.name,
                cli=settings.cli_agent.agent,
            )

    # Jr autopilot subsystem wiring. SnapperRunner spins up a background
    # task that polls each per-CLI signal source (Claude statusline tee,
    # Codex rollout JSONL, opencode SQLite, ...) and atomically writes
    # ``QuotaSnapshot`` files; the autopilot's ``quota_snapshot`` /
    # ``available_clis`` tools then read those files via
    # ProactiveUsageReader. LaunchdScheduler + ScheduledResumeStore back
    # the ``sleep_until`` tool. Telegram defaults to Null (Order 9 will
    # opt-in PTB v22.7 when the operator sets a bot token).
    proactive_reader = ProactiveUsageReader()
    resume_store_for_tools = ScheduledResumeStore(root=_resolve_resume_dir())
    launchd_scheduler_for_tools = LaunchdScheduler() if is_macos() else None
    # Returns a TelegramBridge subclass at runtime; declared `object` in
    # the helper signature so the telegram package import can stay lazy.
    telegram_bridge_for_tools = _build_telegram_bridge()
    # S6 (ADR-006 §4.6) — Self Jr CLI-router control stores. Default YAML
    # paths (shared with the dashboard router) so a ``set_cli_*`` tool call
    # in the round-loop is visible to the dashboard's next select_cli.
    cli_override_store_for_tools = CliOverrideStore(
        sticky_store=default_cli_override_store(),
    )
    cli_runtime_store_for_tools = default_cli_runtime_store()
    snapper_runner = SnapperRunner(
        snappers=build_default_snappers(),
        config=SnapperRunnerConfig(),
    )

    session = Session(
        session_id=session_id,
        prd_text=prd_text,
        prd_path=str(prd_path),
        plan_path_in_sandbox=plan_path_in_sandbox,
        runtime=runtime,
        sandbox=sandbox,
        cli_agent=cli_agent,
        plan_store=plan_store,
        audit_logger=audit_logger,
        lifecycle_config=settings.lifecycle,
        limit_detector=limit_detector,
        rate_limit_handler=_persist_paused_session,
        spawn_handler=spawn_handler,
        tool_registry=tool_registry,
        project_slug=project_slug,
        project_store=project_store_for_tools,
        proactive_reader=proactive_reader,
        launchd_scheduler=launchd_scheduler_for_tools,
        resume_store=resume_store_for_tools,
        cli_override_store=cli_override_store_for_tools,
        cli_runtime_store=cli_runtime_store_for_tools,
        telegram_bridge=telegram_bridge_for_tools,
        theater_producer=theater_producer,
        destructive_whitelist=_load_destructive_whitelist(),
        pending_store=_build_pending_store(
            telegram_bridge=telegram_bridge_for_tools,
        ),
        stuck_detector=StuckDetector(),
        # S-Bridge CORE — Self Jr can now block on AskUserQuestion and
        # resume via Telegram ``/answer``. Construct the store eagerly
        # so the tool registry's handler has somewhere to register
        # pending entries.
        structured_question_store=_build_structured_question_store(),
    )
    # Run the snapper fleet in parallel with the session; tear it down
    # when the session returns (regardless of outcome).
    async with anyio.create_task_group() as tg:
        tg.start_soon(snapper_runner.serve)
        try:
            outcome = await session.run()
        finally:
            snapper_runner.stop()
            if theater_store is not None:
                await theater_store.teardown()

    # S6 (ADR-006 §4.6) — feed the CLI-affinity store the turn-to-complete
    # signal. The dashboard (sole DuckDB writer) drains this JSONL before
    # its next read; here we only append (POSIX O_APPEND is atomic).
    # Skip PAUSED/rate-limit outcomes — they're not a quality signal.
    if project_slug is not None and outcome in (
        SessionState.COMPLETED,
        SessionState.FAILED,
    ):
        from selffork_orchestrator.cli_agent.capabilities import capability_for
        from selffork_orchestrator.router.outcomes import (
            SessionOutcome,
            append_session_outcome,
            default_outcome_log_path,
        )

        _cap = capability_for(settings.cli_agent.agent)
        outcome_model = settings.cli_agent.model or (
            _cap.default_model if _cap is not None else settings.cli_agent.agent
        )
        try:
            append_session_outcome(
                default_outcome_log_path(),
                SessionOutcome(
                    workspace_slug=project_slug,
                    cli=settings.cli_agent.agent,
                    model=outcome_model,
                    succeeded=outcome == SessionState.COMPLETED,
                    turns=session.rounds_completed,
                ),
            )
        except OSError as exc:
            _log.warning("affinity_outcome_write_failed", error=str(exc))
    return outcome, session.failure_reason


def _build_telegram_bridge() -> object:
    """Pick a Telegram bridge based on YAML (S5) > env (legacy).

    Audit-god MEDIUM #5 (2026-05-23): the dashboard wizard writes the
    bot token to ``~/.selffork/settings/telegram.yaml`` via
    :func:`resolve_telegram_config`; the warden must read the same
    source so an operator who configured Telegram from the UI sees
    destructive prompts in their chat. Env still wins when explicitly
    set (``SELFFORK_TELEGRAM_BOT_TOKEN``) so CI / scripted deployments
    aren't broken.

    Returns :class:`PtbTelegramBridge` when (a) a token resolves AND
    (b) ``~/.selffork/operators.json`` has at least one chat_id;
    otherwise :class:`NullTelegramBridge` (safe default,
    ``notify_telegram`` tool calls record intent in audit only).
    """
    from selffork_orchestrator.dashboard.settings import (
        resolve_telegram_config,
    )
    from selffork_orchestrator.telegram import (
        AllowList,
        NullTelegramBridge,
        PtbTelegramBridge,
    )

    cfg = resolve_telegram_config()
    token = cfg.bot_token.strip()
    if not token:
        return NullTelegramBridge()
    allowlist = AllowList.load()
    if not allowlist.chat_ids:
        return NullTelegramBridge()
    try:
        return PtbTelegramBridge(bot_token=token, allowlist=allowlist)
    except Exception:
        return NullTelegramBridge()


def _resolve_pending_audit_path() -> Path:
    """Honour ``SELFFORK_PENDING_AUDIT_PATH`` env var, else use the default.

    Both ``selffork run`` (the producer of destructive requests) and the
    ``selffork ui`` dashboard server (which serves approve/cancel HTTP)
    must point at the same path so the cross-process JSONL replay keeps
    them in sync.
    """
    env = os.environ.get("SELFFORK_PENDING_AUDIT_PATH")
    if env:
        return Path(env).expanduser()
    return _DEFAULT_PENDING_AUDIT_PATH


def _load_destructive_whitelist() -> DestructiveWhitelist:
    """Load the currently-effective destructive whitelist.

    Delegates to the shared resolver so the warden process and the
    dashboard's Settings GET endpoint always look at the same file.

    Precedence (S4):

    1. ``SELFFORK_DESTRUCTIVE_WHITELIST_PATH`` env var (operator pinned).
    2. ``~/.selffork/settings/destructive-whitelist.yaml`` operator
       override (written by the Settings UI editor).
    3. Bundled default at
       ``packages/body/.../data/destructive_actions.yaml``.
    """
    from selffork_orchestrator.dashboard.settings import (
        load_effective_destructive_whitelist,
    )

    return load_effective_destructive_whitelist()


def _build_pending_store(
    telegram_bridge: object | None = None,
) -> PendingConfirmationStore:
    """Construct the destructive pending-confirmation store.

    JSONL audit at :func:`_resolve_pending_audit_path` is the single
    cross-process source of truth — every mutation appends, restart
    replays. The store is restart-safe; the dashboard server's own
    instance reads the same file and so approvals are visible across
    processes (``store.reload_from_disk`` in the dashboard handlers).

    When ``telegram_bridge`` is a non-null bridge we attach an outbound
    notify hook (ADR-006 §4.5 step 1): every request / approve /
    cancel / expire / extend fans out a Telegram message. Hook
    failures (e.g. network) are swallowed inside the store —
    destructive guard correctness must not depend on Telegram.
    """
    store = PendingConfirmationStore(
        audit_path=_resolve_pending_audit_path(),
    )
    if telegram_bridge is not None:
        hook = _build_pending_telegram_hook(telegram_bridge)
        if hook is not None:
            store.set_notify_hook(hook)
    return store


def _build_pending_telegram_hook(telegram_bridge: object) -> Any:
    """Wrap ``bridge.notify(...)`` as a sync :class:`NotifyHook`.

    The store invokes the hook from inside ``request/_decide/expire``
    paths that run on the orchestrator's event loop. We schedule the
    async notify as a background task so the destructive guard never
    blocks on Telegram round-trip time.
    """
    from selffork_orchestrator.telegram.bridge import (
        NullTelegramBridge,
        TelegramBridge,
    )
    from selffork_orchestrator.telegram.destructive_notify import (
        build_message,
    )

    if isinstance(telegram_bridge, NullTelegramBridge):
        return None
    if not isinstance(telegram_bridge, TelegramBridge):
        return None
    bridge = telegram_bridge

    def hook(entry: Any, op: Any) -> None:
        from selffork_orchestrator.telegram.bridge import TelegramMessage

        outbound = build_message(entry, op)
        message = TelegramMessage(
            level=outbound.level,
            text=outbound.text,
            session_id=entry.id,
            project_slug=entry.workspace_slug,
        )
        try:
            # 3.12+: get_event_loop is deprecated outside a coroutine.
            # get_running_loop raises RuntimeError when nothing's
            # running — which is exactly our skip condition for the
            # best-effort fire-and-forget contract (audit fix #3).
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no running loop — skip best-effort notify
        task = loop.create_task(bridge.notify(message))
        _PENDING_TELEGRAM_TASKS.add(task)
        task.add_done_callback(_PENDING_TELEGRAM_TASKS.discard)

    return hook


def _resolve_resume_dir() -> Path:
    """Honour ``SELFFORK_RESUME_DIR`` env var, else use the default."""
    env = os.environ.get("SELFFORK_RESUME_DIR")
    if env:
        return Path(env).expanduser()
    return _DEFAULT_RESUME_DIR


def _resolve_projects_root() -> Path:
    """Honour ``SELFFORK_PROJECTS_ROOT`` env var, else use the default."""
    env = os.environ.get("SELFFORK_PROJECTS_ROOT")
    if env:
        return Path(env).expanduser()
    return _DEFAULT_PROJECTS_ROOT


def _apply_project_routing(
    settings: SelfForkSettings,
    *,
    project_slug: str | None,
    projects_root: Path,
) -> SelfForkSettings:
    """Redirect audit + sandbox dirs under ``projects_root/<slug>``.

    No-op when ``project_slug`` is ``None``. Otherwise both
    ``audit.audit_dir`` and ``sandbox.workspace_root`` are pointed at
    the per-project layout from :class:`ProjectStore`, and the
    directories are materialised so AuditLogger + sandbox can write
    immediately. Closes the TODO captured in
    ``project_run_project_routing_followup.md``.
    """
    if project_slug is None:
        return settings
    from selffork_orchestrator.projects.store import ProjectStore

    store = ProjectStore(root=projects_root)
    audit_dir = store.audit_dir(project_slug)
    workspace_root = store.workspace_root(project_slug)
    audit_dir.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    return settings.model_copy(
        update={
            "audit": settings.audit.model_copy(update={"audit_dir": str(audit_dir)}),
            "sandbox": settings.sandbox.model_copy(
                update={"workspace_root": str(workspace_root)},
            ),
        },
    )


# ── selffork project sub-app ─────────────────────────────────────────────────


project_app = typer.Typer(
    name="project",
    help="Create, list, and inspect SelfFork projects (kanban + sessions).",
    no_args_is_help=True,
    rich_markup_mode=None,
)
app.add_typer(project_app, name="project")
app.add_typer(mind_app, name="mind")


@project_app.command("create")
def project_create(
    name: Annotated[str, typer.Argument(..., help="Human-readable project name.")],
    root_path: Annotated[
        Path | None,
        typer.Option(
            "--root",
            help=(
                "Optional: bind this project to an existing repo on disk. "
                "When set, `selffork run --project <slug>` cwd's into "
                "that path. Otherwise the project gets a fresh sandbox "
                "workspace under ~/.selffork/projects/<slug>/workspaces/."
            ),
        ),
    ] = None,
    description: Annotated[
        str,
        typer.Option("--description", "-d", help="Free-text description."),
    ] = "",
) -> None:
    """Create a new SelfFork project."""
    from selffork_orchestrator.projects.store import ProjectStore

    root = _resolve_projects_root()
    root.mkdir(parents=True, exist_ok=True)
    store = ProjectStore(root=root)
    try:
        project = store.create(
            name=name,
            description=description,
            root_path=str(root_path.expanduser()) if root_path is not None else None,
        )
    except ConfigError as exc:
        typer.echo(f"selffork: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        f"selffork: created project {project.slug!r} ({project.name})\n"
        f"  dir: {root / project.slug}\n"
        f"  root: {project.root_path or '(default sandbox)'}",
    )


@project_app.command("list")
def project_list() -> None:
    """List every project under the projects root."""
    from selffork_orchestrator.projects.store import ProjectStore

    store = ProjectStore(root=_resolve_projects_root())
    projects = store.list_all()
    if not projects:
        typer.echo(
            "selffork: no projects yet — create one with `selffork project create <name>`.",
        )
        raise typer.Exit(code=0)
    for p in projects:
        board = store.load_board(p.slug)
        groups = board.cards_by_column()
        counts = " ".join(f"{col}={len(cards)}" for col, cards in groups.items())
        typer.echo(f"  {p.slug:<24}  {p.name}    [{counts}]")


@project_app.command("show")
def project_show(
    slug: Annotated[str, typer.Argument(..., help="Project slug.")],
) -> None:
    """Print a project's metadata + kanban summary."""
    from selffork_orchestrator.projects.store import ProjectStore

    store = ProjectStore(root=_resolve_projects_root())
    try:
        project = store.load(slug)
    except ConfigError as exc:
        typer.echo(f"selffork: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if project is None:
        typer.echo(f"selffork: project {slug!r} not found.", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"slug:        {project.slug}")
    typer.echo(f"name:        {project.name}")
    typer.echo(f"description: {project.description or '(none)'}")
    typer.echo(f"root_path:   {project.root_path or '(default sandbox)'}")
    typer.echo(f"created_at:  {project.created_at.isoformat()}")
    typer.echo(f"updated_at:  {project.updated_at.isoformat()}")
    typer.echo("kanban:")
    for col, cards in store.load_board(slug).cards_by_column().items():
        typer.echo(f"  {col} ({len(cards)})")
        for card in cards[:5]:
            typer.echo(f"    - {card.title}  [{card.id[:14]}…]")
        if len(cards) > 5:
            typer.echo(f"    … {len(cards) - 5} more")


# ── selffork train ────────────────────────────────────────────────────────────


@app.command()
def train(
    info_only: Annotated[
        bool,
        typer.Option(
            "--info",
            help="Show current adapter info and exit; do not emit a training plan.",
        ),
    ] = False,
    method: Annotated[
        str,
        typer.Option(
            "--method",
            help=(
                "Adapter method — QLoRA (default) | LoRA | Full. The "
                "M7 worker today only ships QLoRA."
            ),
        ),
    ] = "QLoRA",
    dataset_source: Annotated[
        str,
        typer.Option(
            "--dataset",
            help=(
                "``auto`` (session history) or a filesystem path to a "
                "JSONL dataset for the M7 worker."
            ),
        ),
    ] = "auto",
    lora_rank: Annotated[
        int,
        typer.Option("--lora-rank", help="LoRA rank (must be > 0)."),
    ] = 32,
    lora_alpha: Annotated[
        int,
        typer.Option("--lora-alpha", help="LoRA alpha (must be > 0)."),
    ] = 16,
    learning_rate: Annotated[
        str,
        typer.Option(
            "--learning-rate",
            "--lr",
            help="Learning rate string forwarded to the worker (default 2e-4).",
        ),
    ] = "2e-4",
    epochs: Annotated[
        int,
        typer.Option(
            "--epochs",
            help="Number of training epochs (must be > 0).",
        ),
    ] = 3,
    target_modules: Annotated[
        str,
        typer.Option(
            "--target-modules",
            help=(
                "``attention`` (LoRA on attention only) or "
                "``attention+mlp`` (both)."
            ),
        ),
    ] = "attention",
    adapter_manifest: Annotated[
        Path | None,
        typer.Option(
            "--adapter-manifest",
            help=(
                "Manifest path override (defaults to "
                "~/.selffork/reflex/adapters/current/manifest.json)."
            ),
        ),
    ] = None,
) -> None:
    """Reflex pillar fine-tune entry point (M7).

    Reads the canonical adapter manifest at
    ``~/.selffork/reflex/adapters/current/manifest.json`` and reports
    the current adapter state plus what *would* be queued for
    training. The real QLoRA worker lands in M7 (Pillar 1); pre-M7
    this command is a planning + status surface — no weights are
    written, no GPU is held.

    Reflex training is intentionally **out of the dashboard UI** (it
    is a one-shot operation, not a daily-driver dial). Run from a
    shell whenever you want to refresh the adapter; the result lands
    at the manifest path and the Heartbeat filter / dashboard pick it
    up automatically.
    """
    from selffork_orchestrator.reflex_manifest import (
        ADAPTER_MANIFEST_PATH,
        load_adapter_manifest,
    )

    manifest_path = (
        adapter_manifest if adapter_manifest is not None else ADAPTER_MANIFEST_PATH
    )
    manifest = load_adapter_manifest(manifest_path)
    if manifest.trained:
        typer.echo(
            f"Current adapter: version={manifest.version} "
            f"method={manifest.method} "
            f"trained_at={manifest.trained_at} "
            f"age_days={manifest.age_days} "
            f"examples={manifest.examples}",
        )
    else:
        typer.echo(manifest.message or "No adapter trained yet.")

    if info_only:
        raise typer.Exit(code=0)

    valid_methods = {"QLoRA", "LoRA", "Full"}
    if method not in valid_methods:
        typer.echo(
            f"selffork: invalid --method {method!r}; "
            f"expected one of {sorted(valid_methods)}",
            err=True,
        )
        raise typer.Exit(code=2)
    valid_targets = {"attention", "attention+mlp"}
    if target_modules not in valid_targets:
        typer.echo(
            f"selffork: invalid --target-modules {target_modules!r}; "
            f"expected one of {sorted(valid_targets)}",
            err=True,
        )
        raise typer.Exit(code=2)
    if epochs <= 0:
        typer.echo("selffork: --epochs must be > 0", err=True)
        raise typer.Exit(code=2)
    if lora_rank <= 0:
        typer.echo("selffork: --lora-rank must be > 0", err=True)
        raise typer.Exit(code=2)
    if lora_alpha <= 0:
        typer.echo("selffork: --lora-alpha must be > 0", err=True)
        raise typer.Exit(code=2)

    typer.echo("")
    typer.echo("--- training plan (M7 worker stub) ---")
    typer.echo(f"method:         {method}")
    typer.echo(f"dataset:        {dataset_source}")
    typer.echo(f"lora_rank:      {lora_rank}")
    typer.echo(f"lora_alpha:     {lora_alpha}")
    typer.echo(f"learning_rate:  {learning_rate}")
    typer.echo(f"epochs:         {epochs}")
    typer.echo(f"target_modules: {target_modules}")
    typer.echo("")
    typer.echo(
        "Real QLoRA worker lands in M7 (Pillar 1 Reflex). Job not "
        "started; no GPU held. Track progress at "
        "~/.selffork/reflex/adapters/ once M7 ships.",
    )


# ── selffork ui ───────────────────────────────────────────────────────────────


@app.command(name="ui")
def ui(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="Path to a selffork.yaml. Used to resolve audit_dir.",
        ),
    ] = None,
    host: Annotated[
        str,
        typer.Option("--host", help="HTTP bind host."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", min=1, max=65535, help="HTTP bind port."),
    ] = 8765,
    no_open: Annotated[
        bool,
        typer.Option(
            "--no-open",
            help="Don't auto-open the browser on startup.",
        ),
    ] = False,
) -> None:
    """Start the SelfFork dashboard (read-only, no mock data).

    Reads from the configured audit_dir and the resume directory; serves
    a built Next.js bundle at /. If the bundle hasn't been built yet,
    points the user at ``cd apps/web && npm run dev`` and serves
    only the API.
    """
    import uvicorn

    from selffork_orchestrator.dashboard.server import (
        DashboardConfig,
        build_app,
    )

    try:
        settings = load_settings(config)
    except ConfigError as exc:
        typer.echo(f"selffork: configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    audit_dir = Path(settings.audit.audit_dir).expanduser()
    audit_dir.mkdir(parents=True, exist_ok=True)
    resume_dir = _resolve_resume_dir()
    resume_dir.mkdir(parents=True, exist_ok=True)
    projects_root = _resolve_projects_root()
    projects_root.mkdir(parents=True, exist_ok=True)

    selffork_script = Path(sys.executable).parent / "selffork"
    static_dir = _resolve_static_dir()

    dashboard_config = DashboardConfig(
        audit_dir=audit_dir,
        resume_dir=resume_dir,
        projects_root=projects_root,
        selffork_script=selffork_script,
        static_dir=static_dir,
        config_path=config,
    )
    fastapi_app = build_app(dashboard_config)

    typer.echo(f"selffork: dashboard up on http://{host}:{port}")
    typer.echo(f"selffork: audit_dir = {audit_dir}")
    typer.echo(f"selffork: resume_dir = {resume_dir}")
    if static_dir is None:
        typer.echo(
            "selffork: frontend bundle not found "
            "(expected apps/web/out/). Run `cd apps/web && npm run build` "
            "to produce it, or `npm run dev` to use the Next.js dev server.",
        )
    if not no_open:
        try:
            import webbrowser

            webbrowser.open(f"http://{host}:{port}", new=1, autoraise=True)
        except (OSError, RuntimeError) as exc:
            _log.info("ui_open_browser_skipped", reason=str(exc))

    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        log_level=settings.logging.level.lower(),
    )


def _resolve_static_dir() -> Path | None:
    """Best-effort discovery of the built Next.js bundle.

    Looks at ``apps/web/out/`` relative to the orchestrator package
    location (development install) and returns the path if it exists.
    Returns ``None`` otherwise — the dashboard backend handles that
    by serving the API only and pointing the user at ``npm run dev``.
    """
    pkg_dir = Path(__file__).resolve().parent
    repo_root = pkg_dir.parent.parent.parent.parent  # src/selffork_orchestrator → repo
    candidate = repo_root / "apps" / "web" / "out"
    if candidate.is_dir():
        return candidate
    return None


# ── selffork resume sub-app ───────────────────────────────────────────────────


skills_app = typer.Typer(
    name="skills",
    help=(
        "Skill marketplace fan-out — symlink canonical skills into "
        "each wired CLI agent's skills dir."
    ),
    no_args_is_help=True,
)
app.add_typer(skills_app, name="skills")


@skills_app.command("sync")
def skills_sync(
    canonical: Annotated[
        Path | None,
        typer.Option(
            "--canonical",
            help=(
                "Canonical skills source dir (default: "
                "~/.selffork/skills/)."
            ),
        ),
    ] = None,
    target: Annotated[
        list[Path] | None,
        typer.Option(
            "--target",
            help=(
                "Target CLI skills dir (repeatable). Default: the four "
                "wired CLI agents' skills dirs (claude/codex/gemini/opencode)."
            ),
        ),
    ] = None,
) -> None:
    """Symlink every skill under the canonical dir into each target dir.

    Idempotent — re-running is safe. Conflicts (an existing non-skill
    file or symlink to a different source) are reported but never
    overwritten; the operator inspects the conflict list and resolves
    manually.
    """
    from selffork_orchestrator.skills import (
        SkillInstaller,
        default_canonical_skills_dir,
        default_target_cli_dirs,
    )

    installer = SkillInstaller(
        canonical_dir=canonical or default_canonical_skills_dir(),
        target_dirs=target if target else default_target_cli_dirs(),
    )
    if not installer.canonical_dir.is_dir():
        typer.echo(
            f"selffork skills: canonical dir {installer.canonical_dir} "
            "does not exist yet. Create it (or `git clone` your skills "
            "repo into it) and re-run.",
        )
        raise typer.Exit(code=0)

    report = installer.sync_all()

    total_links = sum(len(v) for v in report.installed.values())
    total_skipped = sum(len(v) for v in report.skipped.values())
    total_conflicts = sum(len(v) for v in report.conflicts.values())

    if not (report.installed or report.skipped or report.conflicts):
        typer.echo(
            f"selffork skills: no skills found in {installer.canonical_dir}; "
            "nothing to do.",
        )
        raise typer.Exit(code=0)

    if report.installed:
        typer.echo(f"Installed ({total_links} link{'s' if total_links != 1 else ''}):")
        for name, entries in sorted(report.installed.items()):
            for _target_root, target_link in entries:
                typer.echo(f"  installed  {name:<24}  →  {target_link}")
    if report.skipped:
        suffix = "y" if total_skipped == 1 else "ies"
        typer.echo(
            f"Skipped (already linked) ({total_skipped} entr{suffix}):",
        )
        for name, targets in sorted(report.skipped.items()):
            for target_root in targets:
                typer.echo(f"  skipped    {name:<24}  in  {target_root}")
    if report.conflicts:
        suffix = "y" if total_conflicts == 1 else "ies"
        typer.echo(
            f"Conflicts ({total_conflicts} entr{suffix}):",
            err=True,
        )
        for name, conflict_entries in sorted(report.conflicts.items()):
            for target_root, reason in conflict_entries:
                typer.echo(
                    f"  conflict   {name:<24}  in  {target_root}  ({reason})",
                    err=True,
                )
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


@skills_app.command("list")
def skills_list(
    canonical: Annotated[
        Path | None,
        typer.Option(
            "--canonical",
            help="Canonical skills source dir (default: ~/.selffork/skills/).",
        ),
    ] = None,
) -> None:
    """Print the skills present in the canonical source dir."""
    from selffork_orchestrator.skills import (
        SkillInstaller,
        default_canonical_skills_dir,
        default_target_cli_dirs,
    )

    installer = SkillInstaller(
        canonical_dir=canonical or default_canonical_skills_dir(),
        target_dirs=default_target_cli_dirs(),
    )
    skills = installer.list_skills()
    if not skills:
        typer.echo(
            f"selffork skills: no skills found in {installer.canonical_dir}",
        )
        raise typer.Exit(code=0)
    typer.echo(f"Canonical source: {installer.canonical_dir}")
    typer.echo(f"Skills ({len(skills)}):")
    for path in skills:
        typer.echo(f"  • {path.name}")
    raise typer.Exit(code=0)


resume_app = typer.Typer(
    name="resume",
    help="List, force, or watch scheduled resumes for paused sessions.",
    no_args_is_help=True,
    rich_markup_mode=None,
)
app.add_typer(resume_app, name="resume")


@resume_app.command("list")
def resume_list() -> None:
    """List every paused session and its scheduled resume time."""
    store = ScheduledResumeStore(root=_resolve_resume_dir())
    records = store.list_all()
    if not records:
        typer.echo("selffork: no paused sessions.")
        raise typer.Exit(code=0)
    now = datetime.now(UTC)
    for r in records:
        delta = r.resume_at - now
        if delta.total_seconds() <= 0:
            when = "DUE NOW"
        else:
            when = f"in {_humanize_delta(delta.total_seconds())}"
        typer.echo(
            f"  {r.session_id}  cli={r.cli_agent}  kind={r.kind}  "
            f"resume_at={r.resume_at.isoformat()}  ({when})",
        )


@resume_app.command("now")
def resume_now(
    session_id: Annotated[
        str,
        typer.Argument(..., help="Session ID to resume immediately, regardless of resume_at."),
    ],
) -> None:
    """Force-resume one paused session right now (bypasses ``resume_at``)."""
    store = ScheduledResumeStore(root=_resolve_resume_dir())
    record = store.load(session_id)
    if record is None:
        typer.echo(f"selffork: no paused session with id {session_id!r}.", err=True)
        raise typer.Exit(code=2)
    exit_code = _resume_one(record)
    raise typer.Exit(code=exit_code)


@resume_app.command("watch")
def resume_watch(
    poll_seconds: Annotated[
        int,
        typer.Option(
            "--poll-seconds",
            min=5,
            max=600,
            help="How often to scan for due resumes. Default 30s.",
        ),
    ] = 30,
) -> None:
    """Foreground daemon: poll ``~/.selffork/scheduled/`` and resume due records.

    POSIX-portable. On a server, run under systemd / launchd / nohup —
    SelfFork doesn't ship a launchd plist generator (your target is a
    rented Linux box, not macOS).
    """
    resume_dir = _resolve_resume_dir()
    store = ScheduledResumeStore(root=resume_dir)
    typer.echo(
        f"selffork: resume daemon polling {resume_dir} every {poll_seconds}s; Ctrl-C to stop.",
    )
    try:
        while True:
            due = store.list_due()
            for record in due:
                typer.echo(f"selffork: resuming due session {record.session_id}")
                exit_code = _resume_one(record)
                typer.echo(
                    f"selffork: resume of {record.session_id} returned exit {exit_code}",
                )
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        typer.echo("selffork: resume daemon stopped.")
        raise typer.Exit(code=0) from None


# ── helpers shared by resume commands ─────────────────────────────────────────


def _resume_one(record: ScheduledResume) -> int:
    """Re-invoke ``selffork run`` for a paused record. Returns the child's exit code.

    The child runs as a fresh subprocess so the parent (this watch daemon)
    can keep polling without holding the entire orchestrator stack in
    memory. On success or rate-limit-again, the record is removed only
    on COMPLETED — a re-paused session keeps its slot.
    """
    selffork_script = Path(sys.executable).parent / "selffork"
    cmd: list[str] = [str(selffork_script), "run", record.prd_path]
    if record.config_path:
        cmd.extend(["--config", record.config_path])
    proc = subprocess.run(  # noqa: S603 — explicit, sanitized argv
        cmd,
        check=False,
        env=os.environ,
    )
    if proc.returncode == 0:
        store = ScheduledResumeStore(root=_resolve_resume_dir())
        store.remove(record.session_id)
        last_round_path = _resolve_resume_dir() / f"{record.session_id}.last_round.txt"
        if last_round_path.is_file():
            last_round_path.unlink()
        # Self-uninstall the launchd plist (if any). launchd's
        # StartCalendarInterval has no Year field — without this cleanup the
        # job would re-fire monthly on the same day/time, producing orphan
        # ``selffork resume now <sid>`` invocations after the session
        # already completed. Linux/non-macOS hosts have no plist; skip.
        # Best-effort: orphan plist is annoying but not destructive since
        # the underlying ScheduledResume record is gone.
        if is_macos():
            with contextlib.suppress(LaunchdSchedulerError, OSError):
                LaunchdScheduler().uninstall(record.session_id)
    return proc.returncode


def _humanize_delta(total_seconds: float) -> str:
    """Render a non-negative seconds delta as ``Xh Ym Zs`` for ``resume list``."""
    seconds = int(total_seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, sec = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{sec}s")
    return " ".join(parts)


def _build_structured_question_store() -> (
    PendingStructuredQuestionStore | SqlitePendingStructuredQuestionStore
):
    """Build the S-Bridge pending structured-question store for a run.

    Faz 0 F2: defers to :func:`build_structured_question_store`. The
    factory picks the SQLite backend when ``SELFFORK_STRUCTURED_QUESTION_DB``
    is set so the ``selffork run`` subprocess and the dashboard process
    can share one DB and Telegram ``/answer`` reaches the CLI subprocess.
    Unset env ⇒ in-memory store (legacy behaviour: each ``run`` is a
    separate process with its own instance; Telegram ``/answer`` only
    resolves dashboard-spawned sessions).
    """
    from selffork_orchestrator.tools.structured_question import (
        build_structured_question_store,
    )

    return build_structured_question_store()


def main() -> None:
    """Console-script entrypoint, declared in ``packages/orchestrator/pyproject.toml``."""
    app()


if __name__ == "__main__":
    main()
