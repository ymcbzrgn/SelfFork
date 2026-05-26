"""Body pillar tool surface — 10 ``body_*`` tools for Jr autopilot.

Originally a flat ``tools/body.py`` (~520 LoC, all 10 tools + helpers
in one file). Split into a subpackage during S-ToolFleet Faz 0 so that
the per-action modules stay small (~100-150 LoC each) and the pattern
generalises to the larger fan-out coming in Faz 1+ (mobile / browser /
VR/AR / desktop will follow the same shape).

Layout:

* :mod:`_internal` — shared helpers (``_require_driver``, ``_gate``,
  ``_emit_audit``, ``_invoke``).
* :mod:`interaction` — five mutating tools (click / type / scroll /
  swipe / press_key).
* :mod:`observation` — two read-only tools (screenshot / ax_tree).
* :mod:`lifecycle` — three app/auth tools (app_launch /
  storage_state_save / storage_state_load).

Every Args class + the ``build_body_tools`` factory is re-exported here
so existing imports (``from selffork_orchestrator.tools.body import
build_body_tools``) keep working byte-for-byte through the migration.
"""

from __future__ import annotations

from typing import Any

from selffork_orchestrator.tools.base import ToolSpec
from selffork_orchestrator.tools.body._internal import (
    _emit_audit,
    _gate,
    _invoke,
    _require_driver,
)
from selffork_orchestrator.tools.body.interaction import (
    BodyClickArgs,
    BodyPressKeyArgs,
    BodyScrollArgs,
    BodySwipeArgs,
    BodyTypeArgs,
    _body_click,
    _body_press_key,
    _body_scroll,
    _body_swipe,
    _body_type,
    build_interaction_tools,
)
from selffork_orchestrator.tools.body.lifecycle import (
    BodyAppLaunchArgs,
    BodyStorageStateLoadArgs,
    BodyStorageStateSaveArgs,
    _body_app_launch,
    _body_storage_state_load,
    _body_storage_state_save,
    build_lifecycle_tools,
)
from selffork_orchestrator.tools.body.observation import (
    BodyAxTreeArgs,
    BodyScreenshotArgs,
    _body_ax_tree,
    _body_screenshot,
    build_observation_tools,
)

__all__ = [
    "BodyAppLaunchArgs",
    "BodyAxTreeArgs",
    "BodyClickArgs",
    "BodyPressKeyArgs",
    "BodyScreenshotArgs",
    "BodyScrollArgs",
    "BodyStorageStateLoadArgs",
    "BodyStorageStateSaveArgs",
    "BodySwipeArgs",
    "BodyTypeArgs",
    "build_body_tools",
]


def build_body_tools() -> list[ToolSpec[Any]]:
    """Return the canonical 10-tool body surface for the default registry.

    Order preserved from the pre-Faz-0 flat module so the system prompt
    ordering Self Jr's fine-tune corpus saw stays stable:

    1. body_click          (interaction)
    2. body_type           (interaction)
    3. body_screenshot     (observation)
    4. body_scroll         (interaction)
    5. body_swipe          (interaction)
    6. body_app_launch     (lifecycle)
    7. body_press_key      (interaction)
    8. body_storage_state_save  (lifecycle)
    9. body_storage_state_load  (lifecycle)
    10. body_ax_tree        (observation)
    """
    interaction = {s.name: s for s in build_interaction_tools()}
    observation = {s.name: s for s in build_observation_tools()}
    lifecycle = {s.name: s for s in build_lifecycle_tools()}
    return [
        interaction["body_click"],
        interaction["body_type"],
        observation["body_screenshot"],
        interaction["body_scroll"],
        interaction["body_swipe"],
        lifecycle["body_app_launch"],
        interaction["body_press_key"],
        lifecycle["body_storage_state_save"],
        lifecycle["body_storage_state_load"],
        observation["body_ax_tree"],
    ]
