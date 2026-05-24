"""CLI router HTTP surface — override + affinity + per-CLI config (S6).

ADR-006 §4.6 + ADR-007 §4 S6. Endpoints under ``/api/router``:

* ``POST   /override``             — set a sticky/single-turn cli[+model] override.
* ``GET    /override/{workspace}`` — current override (non-consuming).
* ``DELETE /override/{workspace}`` — clear it.
* ``GET    /affinity/{workspace}`` — scored ``(cli, model)`` candidates +
  active override + resolved efforts (read-only; powers the theater
  "Switch CLI" dropdown + Self Jr's "why this cli/model").
* ``GET    /capabilities``         — per-CLI models + effort levels + the
  per-model-quota flag (what Self Jr / the operator may set).
* ``GET    /config``               — current per-CLI runtime config.
* ``PUT    /config/effort``        — set a CLI's reasoning effort.
* ``PUT    /config/models``        — narrow a CLI's enabled model set.

The override + config write paths back the Talk ``/cli`` chip, the
Telegram ``/cli`` command, the theater dropdown, AND the Self Jr autopilot
tool (operator 2026-05-24: nothing hardcoded — Self Jr mutates these).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from selffork_orchestrator.cli_agent.capabilities import (
    candidate_pairs,
    capability_for,
)
from selffork_orchestrator.router.affinity import CLIRouter

__all__ = [
    "AffinityView",
    "CliCapabilityView",
    "CliRuntimeView",
    "CliScoreView",
    "EffortRequest",
    "EnabledModelsRequest",
    "OverrideRequest",
    "OverrideResponse",
    "build_router_router",
]


class OverrideRequest(BaseModel):
    """Body of ``POST /api/router/override``."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    workspace: str
    cli: str
    model: str | None = None
    sticky: bool = True


class OverrideResponse(BaseModel):
    """Resolved override for one workspace."""

    model_config = ConfigDict(protected_namespaces=())

    workspace: str
    cli: str
    model: str | None
    sticky: bool


class CliScoreView(BaseModel):
    """One ``(cli, model)`` candidate's affinity score (observability)."""

    model_config = ConfigDict(protected_namespaces=())

    cli: str
    model: str
    score: float
    match_level: str
    observations: float
    avg_turns: float | None


class AffinityView(BaseModel):
    """Scored candidates + active override + resolved efforts."""

    workspace: str
    task_type: str | None
    active_override: OverrideResponse | None
    candidates: list[CliScoreView]
    efforts: dict[str, str | None]


class CliCapabilityView(BaseModel):
    """What a CLI can be set to (models + effort levels + quota shape)."""

    model_config = ConfigDict(protected_namespaces=())

    cli: str
    models: list[str]
    default_model: str
    effort_levels: list[str]
    default_effort: str | None
    per_model_quota: bool


class CliRuntimeView(BaseModel):
    """Current Self-Jr-mutable per-CLI runtime config."""

    efforts: dict[str, str]
    enabled_models: dict[str, list[str]]


class EffortRequest(BaseModel):
    """Body of ``PUT /api/router/config/effort``."""

    model_config = ConfigDict(extra="forbid")

    cli: str
    effort: str | None = None


class EnabledModelsRequest(BaseModel):
    """Body of ``PUT /api/router/config/models``."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    cli: str
    models: list[str]


def build_router_router(*, router: CLIRouter) -> APIRouter:
    """Construct the CLI-router API router (ADR-007 §4 S6)."""
    api = APIRouter(prefix="/api/router", tags=["router"])

    def _validate_target(cli: str, model: str | None) -> None:
        if cli not in router.candidates:
            raise HTTPException(
                status_code=400,
                detail=f"unknown cli {cli!r}; expected one of "
                f"{sorted(router.candidates)}",
            )
        if model is not None:
            cap = capability_for(cli)
            if cap is None or not cap.has_model(model):
                raise HTTPException(
                    status_code=400,
                    detail=f"unknown model {model!r} for cli {cli!r}",
                )

    def _runtime_view() -> CliRuntimeView:
        cfg = router.runtime_store.read()
        return CliRuntimeView(
            efforts=dict(cfg.efforts),
            enabled_models={k: list(v) for k, v in cfg.enabled_models.items()},
        )

    # ── overrides ──────────────────────────────────────────────────────

    @api.post("/override", response_model=OverrideResponse)
    def set_override(payload: OverrideRequest) -> OverrideResponse:
        _validate_target(payload.cli, payload.model)
        override = router.override_store.set(
            workspace=payload.workspace,
            cli=payload.cli,
            model=payload.model,
            sticky=payload.sticky,
        )
        return OverrideResponse(
            workspace=override.workspace,
            cli=override.cli,
            model=override.model,
            sticky=override.sticky,
        )

    @api.get("/override/{workspace}", response_model=OverrideResponse | None)
    def get_override(workspace: str) -> OverrideResponse | None:
        override = router.override_store.peek(workspace)
        if override is None:
            return None
        return OverrideResponse(
            workspace=override.workspace,
            cli=override.cli,
            model=override.model,
            sticky=override.sticky,
        )

    @api.delete("/override/{workspace}")
    def clear_override(workspace: str) -> dict[str, bool]:
        return {"cleared": router.override_store.clear(workspace)}

    # ── affinity preview ───────────────────────────────────────────────

    @api.get("/affinity/{workspace}", response_model=AffinityView)
    async def get_affinity(
        workspace: str, task_type: str | None = None
    ) -> AffinityView:
        pairs = candidate_pairs(
            list(router.candidates),
            models_override=router.runtime_store.models_override(),
        )
        await router.affinity.drain()
        resolver = await router.affinity.resolver_for(workspace)
        scored = await resolver.score_candidates(
            task_type=task_type, candidates=pairs
        )
        active = router.override_store.peek(workspace)
        clis = sorted({cli for cli, _ in pairs})
        return AffinityView(
            workspace=workspace,
            task_type=task_type,
            active_override=(
                OverrideResponse(
                    workspace=active.workspace,
                    cli=active.cli,
                    model=active.model,
                    sticky=active.sticky,
                )
                if active is not None
                else None
            ),
            candidates=[
                CliScoreView(
                    cli=s.cli,
                    model=s.model,
                    score=s.score,
                    match_level=s.match_level,
                    observations=s.observations,
                    avg_turns=s.avg_turns,
                )
                for s in scored
            ],
            efforts={cli: router.runtime_store.effort_for(cli) for cli in clis},
        )

    # ── capabilities + config (Self-Jr-mutable) ────────────────────────

    @api.get("/capabilities", response_model=list[CliCapabilityView])
    def get_capabilities() -> list[CliCapabilityView]:
        views: list[CliCapabilityView] = []
        for cli in router.candidates:
            cap = capability_for(cli)
            if cap is None:
                continue
            views.append(
                CliCapabilityView(
                    cli=cap.cli,
                    models=list(cap.models),
                    default_model=cap.default_model,
                    effort_levels=list(cap.effort.levels),
                    default_effort=cap.effort.default,
                    per_model_quota=cap.per_model_quota,
                )
            )
        return views

    @api.get("/config", response_model=CliRuntimeView)
    def get_config() -> CliRuntimeView:
        return _runtime_view()

    @api.put("/config/effort", response_model=CliRuntimeView)
    def put_effort(payload: EffortRequest) -> CliRuntimeView:
        try:
            router.runtime_store.set_effort(
                cli=payload.cli, effort=payload.effort
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _runtime_view()

    @api.put("/config/models", response_model=CliRuntimeView)
    def put_models(payload: EnabledModelsRequest) -> CliRuntimeView:
        try:
            router.runtime_store.set_enabled_models(
                cli=payload.cli, models=payload.models
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _runtime_view()

    return api
