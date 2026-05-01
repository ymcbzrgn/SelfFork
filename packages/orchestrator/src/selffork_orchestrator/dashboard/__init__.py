"""Dashboard HTTP+WebSocket surface for SelfFork.

Read-only views over real on-disk artifacts; ABSOLUTELY no mock data.
See ``project_ui_stack.md``.
"""

from __future__ import annotations

from selffork_orchestrator.dashboard.server import DashboardConfig, build_app

__all__ = ["DashboardConfig", "build_app"]
