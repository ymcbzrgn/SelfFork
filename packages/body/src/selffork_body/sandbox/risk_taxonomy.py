"""Risk taxonomy for the M5 Body permission warden (ADR-005 §M5-D2).

Four-tier classification (T0-T3) drives the per-action approval gate. Each
action carries a default tier; per-session overrides are accepted on
``PermissionWarden.__init__``. Tiers map onto the 3-mode warden:

* ``read_only``: T0 auto-allow, T1+ deny.
* ``workspace_write``: T0/T1 auto-allow, T2/T3 require operator confirmation.
* ``danger_full_access``: T0/T1/T2 auto-allow (logged), T3 still requires
  two-key confirmation.
"""

from __future__ import annotations

from typing import Literal

__all__ = [
    "DEFAULT_ACTION_TIERS",
    "ApprovalGate",
    "RiskTier",
    "tier_for_action",
]


RiskTier = Literal["T0", "T1", "T2", "T3"]
"""Risk classification per action.

* ``T0``: read-only, idempotent (screenshot, scroll, ax_tree).
* ``T1``: local mutation, recoverable (click, type, scroll-with-input).
* ``T2``: high side-effect (shell_exec, install_apk, evaluate_js).
* ``T3``: cost / account risk (payment_form_submit, credential_input).
"""

ApprovalGate = Literal["auto", "on_request", "always_required", "two_key"]
"""How a tier surfaces to the operator.

* ``auto``: warden allows without prompting.
* ``on_request``: prompts only in ``workspace_write`` mode.
* ``always_required``: every invocation requires explicit operator approval.
* ``two_key``: requires both Cockpit + Telegram confirm (T3 default).
"""


# Default tier registry. Per-session overrides accepted by
# ``PermissionWarden(action_tiers=...)``; never mutated globally.
DEFAULT_ACTION_TIERS: dict[str, RiskTier] = {
    # ---- T0 — read-only ----
    "screenshot": "T0",
    "scroll": "T0",
    "ax_tree": "T0",
    "read_dom": "T0",
    "list_processes": "T0",
    "list_apps": "T0",
    "observe": "T0",
    "wait": "T0",
    # ---- T1 — local mutation, recoverable ----
    "click": "T1",
    "double_click": "T1",
    "type": "T1",
    "press_key": "T1",
    "swipe": "T1",
    "navigate": "T1",  # only when target domain is allowlisted
    "workspace_file_write": "T1",
    "tmux_send_keys": "T1",
    "storage_state_load": "T1",
    "storage_state_save": "T1",
    # ---- T2 — high side-effect ----
    "shell_exec": "T2",
    "applescript": "T2",
    "evaluate_js": "T2",
    "file_write_outside_workspace": "T2",
    "navigate_new_domain": "T2",
    "app_launch": "T2",
    "install_apk": "T2",
    "adb_shell": "T2",
    # ---- T3 — cost / account risk ----
    "payment_form_submit": "T3",
    "credential_input": "T3",
    "account_login": "T3",
    "network_egress_unknown_host": "T3",
}


def tier_for_action(action_type: str, overrides: dict[str, RiskTier] | None = None) -> RiskTier:
    """Resolve the risk tier for ``action_type``.

    Unknown actions default to ``T2`` (conservative — operator confirmation
    required) rather than raising; this keeps new driver actions safe before
    they're explicitly registered.
    """
    if overrides and action_type in overrides:
        return overrides[action_type]
    return DEFAULT_ACTION_TIERS.get(action_type, "T2")
