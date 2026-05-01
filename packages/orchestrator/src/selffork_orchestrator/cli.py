"""``selffork`` user-facing CLI.

Single subcommand: ``selffork run <prd-path>``. Wires every collaborator
(runtime, sandbox, CLI agent, plan store, audit logger) and drives one
:class:`Session` end-to-end. Exits ``0`` on COMPLETED, ``1`` on FAILED,
``2`` on usage / config errors before the session even starts.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §17 step 8.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from selffork_orchestrator import __version__
from selffork_orchestrator.cli_agent.factory import build_cli_agent
from selffork_orchestrator.lifecycle.session import Session
from selffork_orchestrator.lifecycle.states import SessionState
from selffork_orchestrator.plan.factory import build_plan_store
from selffork_orchestrator.runtime.factory import build_runtime
from selffork_orchestrator.sandbox.factory import build_sandbox
from selffork_shared.audit import AuditLogger
from selffork_shared.config import SelfForkSettings, load_settings
from selffork_shared.errors import ConfigError, SelfForkError
from selffork_shared.logging import bind_correlation_id, bind_session_id, get_logger, setup_logging
from selffork_shared.ulid import new_ulid

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

    try:
        outcome, failure_reason = asyncio.run(_amain(settings, prd, prd_text, session_id))
    except SelfForkError as exc:
        typer.echo(f"selffork: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if outcome == SessionState.COMPLETED:
        typer.echo(f"selffork: session {session_id} completed successfully.")
        raise typer.Exit(code=0)
    typer.echo(
        f"selffork: session {session_id} failed: {failure_reason or 'unknown reason'}",
        err=True,
    )
    raise typer.Exit(code=1)


async def _amain(
    settings: SelfForkSettings,
    prd_path: Path,
    prd_text: str,
    session_id: str,
) -> tuple[SessionState, str | None]:
    """Async orchestrator. Returns (outcome, failure_reason)."""
    audit_logger = AuditLogger(settings.audit, session_id=session_id)
    runtime = build_runtime(settings.runtime)
    sandbox = build_sandbox(settings.sandbox, session_id=session_id)
    cli_agent = build_cli_agent(settings.cli_agent)

    # Pre-spawn the sandbox so we can build the plan store with a concrete
    # workspace path. ``Session._prepare`` will call ``spawn()`` again —
    # both ``SubprocessSandbox`` and ``DockerSandbox`` are idempotent on
    # repeated spawn.
    await sandbox.spawn()

    plan_store = build_plan_store(
        settings.plan,
        workspace_path=sandbox.host_workspace_path,
    )
    plan_path_in_sandbox = str(Path(sandbox.workspace_path) / settings.plan.plan_filename)

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
    )
    outcome = await session.run()
    return outcome, session.failure_reason


def main() -> None:
    """Console-script entrypoint, declared in ``packages/orchestrator/pyproject.toml``."""
    app()


if __name__ == "__main__":
    main()
