"""Self Jr CLI-router control + introspection tools — S6 (ADR-006 §4.6).

Self Jr manages its own CLI fleet natively: which CLI (+ optional model)
handles a workspace, and each CLI's reasoning-effort + enabled-model
subset. These tools both **read** and **write** the same Self-Jr-mutable
stores the operator UI writes
(:mod:`selffork_orchestrator.router.override` +
:mod:`selffork_orchestrator.router.cli_config`), so a round-loop decision
and an operator decision share one source of truth.

> "Self Jr native ne isterse kullansin, kendisi degistirsin, en iyisini
> O bilir." / "readler ile okuma da yapabilmesi lazim." — operator
> 2026-05-24. The UI is secondary; this is the native path.

Timing: a write here changes the NEXT autonomous selection, not the
running round. The active session's CLI/model/effort was fixed when the
router spawned it; the change lands on the next ``select_cli`` (the
heartbeat selector / task-starter). Mid-session live model-swap is out of
scope (it would require re-spawning the CLIAgent).

Cross-process: the round-loop runs inside a ``selffork run`` subprocess
while the router runs in the dashboard process. Only file-backed state
crosses that boundary, so overrides are written **sticky** (persisted
YAML) — a single-turn (in-memory) override would never reach the
dashboard router. Reads hit the same default YAML the dashboard writes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict, Field

from selffork_orchestrator.cli_agent.capabilities import CAPABILITIES, capability_for
from selffork_orchestrator.tools.base import (
    ToolArgs,
    ToolContext,
    ToolSpec,
    raise_unauthorized,
)

if TYPE_CHECKING:
    from selffork_orchestrator.router import CliOverrideStore, CliRuntimeStore

__all__ = ["build_router_tools"]


# ── store resolvers (None-guard + isinstance-narrow, per kanban._store) ─────────


def _require_override_store(ctx: ToolContext) -> CliOverrideStore:
    """Return the wired override store, or refuse with ``unauthorized``."""
    from selffork_orchestrator.router import CliOverrideStore

    store = ctx.cli_override_store
    if store is None:
        raise_unauthorized(
            "CLI override control requires cli_override_store to be wired "
            "(None here); `selffork run` injects it at boot.",
        )
        raise AssertionError("unreachable")
    if not isinstance(store, CliOverrideStore):
        raise TypeError(
            "ToolContext.cli_override_store is not a CliOverrideStore",
        )
    return store


def _require_runtime_store(ctx: ToolContext) -> CliRuntimeStore:
    """Return the wired runtime store, or refuse with ``unauthorized``."""
    from selffork_orchestrator.router import CliRuntimeStore

    store = ctx.cli_runtime_store
    if store is None:
        raise_unauthorized(
            "CLI runtime control requires cli_runtime_store to be wired "
            "(None here); `selffork run` injects it at boot.",
        )
        raise AssertionError("unreachable")
    if not isinstance(store, CliRuntimeStore):
        raise TypeError(
            "ToolContext.cli_runtime_store is not a CliRuntimeStore",
        )
    return store


# ── set_cli_override ────────────────────────────────────────────────────────────


class _SetOverrideArgs(ToolArgs):
    """Args for ``set_cli_override``."""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    workspace: str = Field(..., min_length=1)
    cli: str = Field(..., min_length=1)
    model: str | None = Field(
        default=None,
        description="Optional model inside the CLI; omit to let affinity pick.",
    )


def _set_cli_override_handler(
    ctx: ToolContext,
    args: _SetOverrideArgs,
) -> dict[str, Any]:
    store = _require_override_store(ctx)
    cap = capability_for(args.cli)
    if cap is None:
        return {
            "applied": False,
            "error": f"unknown cli {args.cli!r}; known: {sorted(CAPABILITIES)}",
        }
    if args.model is not None and not cap.has_model(args.model):
        return {
            "applied": False,
            "error": (
                f"cli {args.cli!r} has no model {args.model!r}; "
                f"models: {list(cap.models)}"
            ),
        }
    override = store.set(
        workspace=args.workspace,
        cli=args.cli,
        model=args.model,
        sticky=True,
    )
    return {
        "applied": True,
        "workspace": override.workspace,
        "cli": override.cli,
        "model": override.model,
        "sticky": True,
        "effective": "next autonomous selection for this workspace",
    }


# ── clear_cli_override ──────────────────────────────────────────────────────────


class _ClearOverrideArgs(ToolArgs):
    """Args for ``clear_cli_override``."""

    workspace: str = Field(..., min_length=1)


def _clear_cli_override_handler(
    ctx: ToolContext,
    args: _ClearOverrideArgs,
) -> dict[str, Any]:
    store = _require_override_store(ctx)
    cleared = store.clear(args.workspace)
    return {"cleared": cleared, "workspace": args.workspace}


# ── set_cli_effort ──────────────────────────────────────────────────────────────


class _SetEffortArgs(ToolArgs):
    """Args for ``set_cli_effort``."""

    cli: str = Field(..., min_length=1)
    effort: str | None = Field(
        default=None,
        description="Effort level; None resets to the CLI's own default.",
    )


def _set_cli_effort_handler(
    ctx: ToolContext,
    args: _SetEffortArgs,
) -> dict[str, Any]:
    store = _require_runtime_store(ctx)
    try:
        store.set_effort(cli=args.cli, effort=args.effort)
    except ValueError as exc:
        return {"applied": False, "error": str(exc)}
    return {
        "applied": True,
        "cli": args.cli,
        "effort": args.effort,
        "effective": "next autonomous selection",
    }


# ── set_cli_models ──────────────────────────────────────────────────────────────


class _SetModelsArgs(ToolArgs):
    """Args for ``set_cli_models``."""

    cli: str = Field(..., min_length=1)
    models: list[str] = Field(
        default_factory=list,
        description="Allowed model subset for this CLI; empty resets to all.",
    )


def _set_cli_models_handler(
    ctx: ToolContext,
    args: _SetModelsArgs,
) -> dict[str, Any]:
    store = _require_runtime_store(ctx)
    try:
        store.set_enabled_models(cli=args.cli, models=args.models)
    except ValueError as exc:
        return {"applied": False, "error": str(exc)}
    return {
        "applied": True,
        "cli": args.cli,
        "enabled_models": args.models,
        "effective": "narrows router candidates for this cli",
    }


# ── reads ───────────────────────────────────────────────────────────────────────


class _NoArgs(ToolArgs):
    """No arguments."""


def _cli_capabilities_handler(
    ctx: ToolContext,
    args: _NoArgs,
) -> dict[str, Any]:
    return {
        "clis": {
            cli: {
                "models": list(cap.models),
                "default_model": cap.default_model,
                "effort_levels": list(cap.effort.levels),
                "effort_default": cap.effort.default,
                "per_model_quota": cap.per_model_quota,
            }
            for cli, cap in CAPABILITIES.items()
        },
    }


def _cli_config_handler(
    ctx: ToolContext,
    args: _NoArgs,
) -> dict[str, Any]:
    store = _require_runtime_store(ctx)
    cfg = store.read()
    return {
        "efforts": dict(cfg.efforts),
        "enabled_models": {
            cli: list(models) for cli, models in cfg.enabled_models.items()
        },
        "resolved_efforts": {cli: store.effort_for(cli) for cli in CAPABILITIES},
    }


class _OverrideQueryArgs(ToolArgs):
    """Args for ``cli_override``."""

    workspace: str = Field(..., min_length=1)


def _cli_override_handler(
    ctx: ToolContext,
    args: _OverrideQueryArgs,
) -> dict[str, Any]:
    store = _require_override_store(ctx)
    override = store.peek(args.workspace)
    if override is None:
        return {"workspace": args.workspace, "override": None}
    return {
        "workspace": args.workspace,
        "override": {
            "cli": override.cli,
            "model": override.model,
            "sticky": override.sticky,
        },
    }


# ── cli_affinity (reader-pattern snapshot) ──────────────────────────────────────


class _AffinityQueryArgs(ToolArgs):
    """Args for ``cli_affinity``."""

    workspace: str = Field(..., min_length=1)


def _cli_affinity_handler(
    ctx: ToolContext,
    args: _AffinityQueryArgs,
) -> dict[str, Any]:
    from selffork_orchestrator.router.affinity_snapshot import (
        read_affinity_snapshot,
    )

    snapshot = read_affinity_snapshot(args.workspace)
    if snapshot is None:
        return {
            "workspace": args.workspace,
            "available": False,
            "reason": (
                "no affinity snapshot yet for this workspace; the router "
                "writes one when it next selects a CLI here."
            ),
        }
    return {"workspace": args.workspace, "available": True, "affinity": snapshot}


# ── registry helper ─────────────────────────────────────────────────────────────


def build_router_tools() -> list[ToolSpec[Any]]:
    """Self Jr CLI-router control + introspection tools (S6)."""
    return [
        ToolSpec(
            name="set_cli_override",
            description=(
                "Force the router to use a specific CLI (and optionally a "
                "model inside it) for a workspace, beating quota + affinity. "
                "Sticky: persists until cleared. Takes effect on the NEXT "
                "autonomous selection, not the current round. Use when a task "
                "needs a particular CLI/model."
            ),
            args_model=_SetOverrideArgs,
            handler=_set_cli_override_handler,
        ),
        ToolSpec(
            name="clear_cli_override",
            description=(
                "Remove the sticky CLI override for a workspace so the router "
                "returns to quota + affinity selection."
            ),
            args_model=_ClearOverrideArgs,
            handler=_clear_cli_override_handler,
        ),
        ToolSpec(
            name="set_cli_effort",
            description=(
                "Set a CLI's reasoning-effort level (e.g. claude-code "
                "low|medium|high|xhigh|max). None resets to the CLI default. "
                "Applies to the next selection. Rejected if the level is "
                "unsupported by that CLI."
            ),
            args_model=_SetEffortArgs,
            handler=_set_cli_effort_handler,
        ),
        ToolSpec(
            name="set_cli_models",
            description=(
                "Narrow the model subset the router may route to for a CLI "
                "(empty list resets to all capability models). Rejected for "
                "unknown models."
            ),
            args_model=_SetModelsArgs,
            handler=_set_cli_models_handler,
        ),
        ToolSpec(
            name="cli_capabilities",
            description=(
                "Read the static capability menu: for each CLI its models, "
                "default model, effort levels/default, and whether quota is "
                "per-model. Use to discover what you can route to."
            ),
            args_model=_NoArgs,
            handler=_cli_capabilities_handler,
        ),
        ToolSpec(
            name="cli_config",
            description=(
                "Read the current Self-Jr-mutable runtime config: per-CLI "
                "effort overrides, enabled-model subsets, and the resolved "
                "effort each CLI would use right now."
            ),
            args_model=_NoArgs,
            handler=_cli_config_handler,
        ),
        ToolSpec(
            name="cli_override",
            description=(
                "Read the active sticky CLI override for a workspace (or null "
                "if none). Shows what the router will force on the next "
                "selection."
            ),
            args_model=_OverrideQueryArgs,
            handler=_cli_override_handler,
        ),
        ToolSpec(
            name="cli_affinity",
            description=(
                "Read the affinity landscape for a workspace: each (cli, "
                "model)'s learned success score + match level, the chosen "
                "pair, and quota-filtered candidates. Use to see which CLI/"
                "model has performed best before overriding. Returns "
                "available=false until the router has selected here once."
            ),
            args_model=_AffinityQueryArgs,
            handler=_cli_affinity_handler,
        ),
    ]
