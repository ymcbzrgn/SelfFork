"""Teacher-authored tool-mastery scenarios, one module per tool / category.

Each module exposes ``SCENARIOS: list[ToolScenario]``. The authored content
(situation, chosen action, reasoning) is written by the teacher — kanban +
android_lifecycle by Claude directly; phones / browser / xr_native /
workflow_control by the Fable model (its sharp reasoning, gate-validated). The
:mod:`selffork_orchestrator.corpus.builder` renders + gates every one so only
runtime-valid, canonical tool calls reach the corpus.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.authored import (
    android_lifecycle,
    browser,
    browser_workflow_deep,
    complex_tools,
    kanban,
    memory_context,
    phones,
    phones_deep,
    trajectories_crossdomain,
    trajectories_device,
    trajectories_mobile,
    trajectories_recovery,
    trajectories_workflow,
    workflow_control,
    xr_native,
)
from selffork_orchestrator.corpus.builder import AgenticTrajectory, ToolScenario

# Single-call scenario banks. New tool banks append here.
ALL_SCENARIOS: list[ToolScenario] = [
    *android_lifecycle.SCENARIOS,
    *kanban.SCENARIOS,
    *phones.SCENARIOS,
    *browser.SCENARIOS,
    *xr_native.SCENARIOS,
    *workflow_control.SCENARIOS,
    *complex_tools.SCENARIOS,
    *memory_context.SCENARIOS,
    *phones_deep.SCENARIOS,
    *browser_workflow_deep.SCENARIOS,
]

# Agentic multi-tool trajectory banks (act -> observe -> act -> ... done).
ALL_TRAJECTORIES: list[AgenticTrajectory] = [
    *trajectories_mobile.TRAJECTORIES,
    *trajectories_device.TRAJECTORIES,
    *trajectories_workflow.TRAJECTORIES,
    *memory_context.TRAJECTORIES,
    *trajectories_recovery.TRAJECTORIES,
    *trajectories_crossdomain.TRAJECTORIES,
]

__all__ = ["ALL_SCENARIOS", "ALL_TRAJECTORIES"]
