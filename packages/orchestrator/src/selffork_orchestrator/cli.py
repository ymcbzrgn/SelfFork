"""``selffork`` user-facing CLI.

Single subcommand: ``selffork run <prd-path>``. Wires every collaborator
(runtime, sandbox, CLI agent, plan store, audit logger) and drives one
:class:`Session` end-to-end. Exits ``0`` on COMPLETED, ``1`` on FAILED,
``2`` on usage / config errors before the session even starts.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §17 step 8.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from selffork_orchestrator import __version__
from selffork_orchestrator.cli_agent.factory import build_cli_agent
from selffork_orchestrator.lifecycle.session import Session
from selffork_orchestrator.lifecycle.states import SessionState
from selffork_orchestrator.limits.base import RateLimited
from selffork_orchestrator.limits.factory import build_limit_detector
from selffork_orchestrator.plan.factory import build_plan_store
from selffork_orchestrator.resume.store import ScheduledResume, ScheduledResumeStore
from selffork_orchestrator.runtime.factory import build_runtime
from selffork_orchestrator.runtime.mlx_server import MlxServerRuntime
from selffork_orchestrator.sandbox.factory import build_sandbox
from selffork_orchestrator.spawn.runner import SpawnRunnerConfig, TmuxSpawnRunner
from selffork_orchestrator.tmux.factory import build_tmux_driver
from selffork_shared.audit import AuditLogger
from selffork_shared.config import SelfForkSettings, load_settings
from selffork_shared.errors import ConfigError, SelfForkError
from selffork_shared.logging import bind_correlation_id, bind_session_id, get_logger, setup_logging
from selffork_shared.ulid import new_ulid

# Default location of scheduled-resume records. Each paused session is
# one JSON file under here. Override via ``SELFFORK_RESUME_DIR`` env var.
_DEFAULT_RESUME_DIR = Path("~/.selffork/scheduled").expanduser()
_DEFAULT_PROJECTS_ROOT = Path("~/.selffork/projects").expanduser()

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
    from selffork_orchestrator.projects.store import ProjectStore as _ProjectStore
    from selffork_orchestrator.tools import build_default_registry

    tool_registry = build_default_registry()
    project_store_for_tools: _ProjectStore | None = None
    if project_slug is not None:
        project_store_for_tools = _ProjectStore(root=projects_root)

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
    )
    outcome = await session.run()
    return outcome, session.failure_reason


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


def main() -> None:
    """Console-script entrypoint, declared in ``packages/orchestrator/pyproject.toml``."""
    app()


if __name__ == "__main__":
    main()
