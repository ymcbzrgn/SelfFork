"""Heartbeat HTTP surface — autonomy settings + daemon state (S-Auto Faz G).

ADR-008 §5.5: every Heartbeat behaviour is settable from a UI; the
backend surface lives here. Two endpoint groups:

* ``/api/heartbeat/autonomy`` — persisted :class:`AutonomySettings`.
  ``GET`` returns the current YAML-backed settings (or the default
  ``Dengeli`` preset when nothing is persisted yet); ``PUT`` overwrites
  the file; ``POST .../preset/{name}`` applies a named preset.
* ``/api/heartbeat/state`` — live daemon snapshot (tick count, last
  legal set, last decision, last result, last AIR alert). Read-only —
  the daemon is observed, not controlled, through this endpoint.

PUT semantics: persist now, effect on next daemon restart. Hot-reload
is deferred — keeping Faz G surgical.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from selffork_orchestrator.heartbeat.autonomy import (
    AutonomyPreset,
    AutonomySettings,
    AutonomyStore,
    apply_preset,
)
from selffork_orchestrator.heartbeat.scheduler import HeartbeatScheduler

__all__ = [
    "HeartbeatStateResponse",
    "build_heartbeat_router",
]


class HeartbeatStateResponse(BaseModel):
    """Read-only live snapshot of the running daemon."""

    state: str
    is_running: bool
    tick_count: int
    last_legal_actions: list[str] | None
    last_decision: dict[str, Any] | None
    last_result: dict[str, Any] | None
    last_air_alert: dict[str, Any] | None


def build_heartbeat_router(
    *,
    store: AutonomyStore,
    scheduler: HeartbeatScheduler | None = None,
) -> APIRouter:
    """Construct the Heartbeat API router.

    ``scheduler`` is optional — when the dashboard runs with the
    daemon disabled (``SELFFORK_HEARTBEAT_ENABLED=false``) the state
    endpoint reports a clean "inactive" rather than 503'ing.
    """
    router = APIRouter(prefix="/api/heartbeat", tags=["heartbeat"])

    @router.get("/autonomy", response_model=AutonomySettings)
    def get_autonomy() -> AutonomySettings:
        return store.read_or_default()

    @router.put("/autonomy", response_model=AutonomySettings)
    def put_autonomy(payload: AutonomySettings) -> AutonomySettings:
        store.write(payload)
        return payload

    @router.post(
        "/autonomy/preset/{preset}", response_model=AutonomySettings
    )
    def post_preset(preset: str) -> AutonomySettings:
        try:
            tier = AutonomyPreset(preset)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"unknown preset {preset!r}; "
                    f"expected one of {[p.value for p in AutonomyPreset]}"
                ),
            ) from exc
        settings = apply_preset(tier)
        store.write(settings)
        return settings

    @router.get("/state", response_model=HeartbeatStateResponse)
    def get_state() -> HeartbeatStateResponse:
        if scheduler is None:
            return HeartbeatStateResponse(
                state="disabled",
                is_running=False,
                tick_count=0,
                last_legal_actions=None,
                last_decision=None,
                last_result=None,
                last_air_alert=None,
            )
        legal: list[str] | None = None
        if scheduler.last_legal_actions is not None:
            legal = sorted(a.value for a in scheduler.last_legal_actions)
        decision_payload: dict[str, Any] | None = None
        if scheduler.last_action_decision is not None:
            decision_payload = {
                "action": scheduler.last_action_decision.action.value,
                "reasoning": scheduler.last_action_decision.reasoning,
                "fallback": scheduler.last_action_decision.fallback,
                "selected_at": (
                    scheduler.last_action_decision.selected_at.isoformat()
                ),
            }
        result_payload: dict[str, Any] | None = None
        if scheduler.last_action_result is not None:
            r = scheduler.last_action_result
            result_payload = {
                "action": r.action.value,
                "outcome": r.outcome,
                "summary": r.summary,
                "metadata": dict(r.metadata),
                "executed_at": r.executed_at.isoformat(),
            }
        air_payload: dict[str, Any] | None = None
        if scheduler.last_air_alert is not None:
            a = scheduler.last_air_alert
            air_payload = {
                "severity": a.severity,
                "reason": a.reason,
                "matched_keywords": list(a.matched_keywords),
                "consecutive_failures": a.consecutive_failures,
                "detected_at": a.detected_at.isoformat(),
                "recommended_recovery": a.recommended_recovery,
            }
        return HeartbeatStateResponse(
            state=scheduler.state.value,
            is_running=scheduler.is_running,
            tick_count=scheduler.tick_count,
            last_legal_actions=legal,
            last_decision=decision_payload,
            last_result=result_payload,
            last_air_alert=air_payload,
        )

    return router
