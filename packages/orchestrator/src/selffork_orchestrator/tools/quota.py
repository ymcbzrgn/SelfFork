"""Jr autopilot — quota / health observation tools.

Read-only tools the autopilot calls before deciding to rotate or sleep.

- ``quota_snapshot``: read normalized snapshot for one CLI or every CLI
- ``available_clis``: enumerate registered CLIs + per-CLI health summary
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from selffork_orchestrator.snappers.factory import registered_snapper_ids
from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.usage.proactive import ProactiveUsageReader
from selffork_shared.quota import QuotaSnapshot

__all__ = ["build_quota_tools"]


# ── quota_snapshot ────────────────────────────────────────────────────────────


class _QuotaSnapshotArgs(ToolArgs):
    """Args for ``quota_snapshot``."""

    cli_id: str | None = Field(
        default=None,
        description="Specific CLI id to query; None returns every fresh snapshot.",
    )


def _quota_snapshot_handler(
    ctx: ToolContext,
    args: _QuotaSnapshotArgs,
) -> dict[str, Any]:
    reader = _resolve_reader(ctx)
    if args.cli_id is not None:
        snap = reader.read(args.cli_id)
        return {
            "cli_id": args.cli_id,
            "snapshot": _serialize_snapshot(snap),
        }
    snapshots = reader.read_all()
    return {
        "snapshots": {cli: _serialize_snapshot(s) for cli, s in snapshots.items()},
        "fresh_count": len(snapshots),
    }


# ── available_clis ─────────────────────────────────────────────────────────────


class _AvailableCLIsArgs(ToolArgs):
    """No args. Returns the full registered fleet + per-CLI health."""


def _available_clis_handler(
    ctx: ToolContext,
    _args: _AvailableCLIsArgs,
) -> dict[str, Any]:
    reader = _resolve_reader(ctx)
    snapshots = reader.read_all()
    rows: list[dict[str, Any]] = []
    for cli_id in registered_snapper_ids():
        snap = snapshots.get(cli_id)
        if snap is None:
            rows.append(
                {
                    "cli_id": cli_id,
                    "status": "unknown",
                    "exhausted": False,
                    "reason": "no fresh snapshot — snapper down or never ran",
                    "age_seconds": None,
                },
            )
            continue
        # Empty-windows snapshot means the snapper confirmed auth state but
        # has NOT yet polled the provider's quota endpoint (mmx Token Plan,
        # Z.AI /v1/usage). Reporting "ok" here would lie — the provider
        # could be fully drained. Surface this as ``auth_only`` so the
        # autopilot routes a probing request rather than committing real
        # work to a CLI whose quota status is unknown.
        if not snap.windows:
            rows.append(
                {
                    "cli_id": cli_id,
                    "status": "auth_only",
                    "exhausted": False,
                    "reason": "snapshot present but quota windows not populated",
                    "age_seconds": round(snap.age_seconds(), 1),
                },
            )
            continue
        exhausted = snap.is_exhausted()
        rows.append(
            {
                "cli_id": cli_id,
                "status": "exhausted" if exhausted else "ok",
                "exhausted": exhausted,
                "reason": "one or more windows >= 95%" if exhausted else None,
                "age_seconds": round(snap.age_seconds(), 1),
            },
        )
    return {"clis": rows, "active_cli": ctx.cli_agent_name}


# ── Helpers ────────────────────────────────────────────────────────────────────


def _resolve_reader(ctx: ToolContext) -> ProactiveUsageReader:
    """Pull a reader from context or fall back to a default-config reader.

    Default fallback reads ``~/.selffork/cli-state/`` directly — the
    canonical SnapperRunner output dir. Lets autopilot tools function
    even when the orchestrator hasn't wired a custom reader (e.g. early
    M3 dev, ad-hoc CLI debugging).
    """
    reader = ctx.proactive_reader
    if isinstance(reader, ProactiveUsageReader):
        return reader
    return ProactiveUsageReader()


def _serialize_snapshot(snap: QuotaSnapshot | None) -> dict[str, Any] | None:
    if snap is None:
        return None
    return snap.model_dump(mode="json")


# ── Registry helper ────────────────────────────────────────────────────────────


def build_quota_tools() -> list[ToolSpec[Any]]:
    """Return the canonical quota / health observation tools."""
    return [
        ToolSpec(
            name="quota_snapshot",
            description=(
                "Read the proactive QuotaSnapshot for a CLI agent (or every "
                "CLI when cli_id is omitted). Returns per-window used_pct + "
                "resets_at + context-window state. Call BEFORE rotating or "
                "sleeping to confirm whether quota is actually exhausted."
            ),
            args_model=_QuotaSnapshotArgs,
            handler=_quota_snapshot_handler,
        ),
        ToolSpec(
            name="available_clis",
            description=(
                "Enumerate every registered CLI agent and its current "
                "health (ok / exhausted / unknown). Use to pick the next "
                "rotation target."
            ),
            args_model=_AvailableCLIsArgs,
            handler=_available_clis_handler,
        ),
    ]
