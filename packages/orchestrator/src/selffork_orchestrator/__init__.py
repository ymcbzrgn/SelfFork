"""SelfFork Orchestrator — the first pillar to land in MVP v0.

Owns the four core contracts (LLMRuntime, Sandbox, CLIAgent, PlanStore),
the session lifecycle state machine, and the user-facing ``selffork`` CLI.

See: ``docs/decisions/ADR-001_MVP_v0.md``.
"""

from __future__ import annotations

__version__ = "0.0.1"
