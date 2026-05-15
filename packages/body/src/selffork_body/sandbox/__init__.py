"""Body pillar action-level sandbox (M5 — ADR-005 §M5-D2).

This package's sandbox/ is action-level (per-tool-call permission gating). The
orchestrator-level sandbox (env isolation) lives in
``packages/orchestrator/sandbox/``. Different concerns; no shared interface.

Public surface:

* :class:`PermissionWarden` — 3-mode state machine + 4-tier risk taxonomy.
* :class:`BodyWatchdog` — duration / idle caps + SIGKILL kill-switch.
* :data:`DEFAULT_ACTION_TIERS` — registered action → tier map.
"""

from __future__ import annotations

from selffork_body.sandbox.kill_switch import BodyWatchdog, WatchedSession
from selffork_body.sandbox.risk_taxonomy import (
    DEFAULT_ACTION_TIERS,
    ApprovalGate,
    RiskTier,
    tier_for_action,
)
from selffork_body.sandbox.warden import (
    PermissionDecision,
    PermissionRequest,
    PermissionWarden,
    WardenMode,
    WardenState,
    build_request,
    normalize_domain,
)

__all__ = [
    "DEFAULT_ACTION_TIERS",
    "ApprovalGate",
    "BodyWatchdog",
    "PermissionDecision",
    "PermissionRequest",
    "PermissionWarden",
    "RiskTier",
    "WardenMode",
    "WardenState",
    "WatchedSession",
    "build_request",
    "normalize_domain",
    "tier_for_action",
]
