"""Teacher-authored tool-mastery scenarios, one module per tool / category.

Each module exposes ``SCENARIOS: list[ToolScenario]``. The authored content
(situation, chosen action, reasoning) is written by the teacher (Claude); the
:mod:`selffork_orchestrator.corpus.builder` renders + gates every one so only
runtime-valid, canonical tool calls reach the corpus.
"""

from __future__ import annotations

from selffork_orchestrator.corpus.authored import kanban
from selffork_orchestrator.corpus.builder import ToolScenario

# Registry of all authored scenario banks. New tool banks append here.
ALL_SCENARIOS: list[ToolScenario] = [
    *kanban.SCENARIOS,
]

__all__ = ["ALL_SCENARIOS"]
