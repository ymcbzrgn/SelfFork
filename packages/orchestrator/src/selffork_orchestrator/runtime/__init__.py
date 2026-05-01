"""LLM runtime adapters.

A runtime brings up a local model behind an OpenAI-compatible HTTP API.
Backends live in this package; pick one with :func:`build_runtime`.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.1.
"""

from __future__ import annotations

from selffork_orchestrator.runtime.base import LLMRuntime
from selffork_orchestrator.runtime.factory import build_runtime
from selffork_orchestrator.runtime.mlx_server import MlxServerRuntime

__all__ = ["LLMRuntime", "MlxServerRuntime", "build_runtime"]
