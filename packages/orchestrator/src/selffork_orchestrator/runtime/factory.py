"""Backend → implementation resolver for :class:`LLMRuntime`.

Single-entry point so callers don't have to know which class implements
which backend. Stubbed backends raise :class:`NotImplementedError` from
their constructors; this function lets that propagate.
"""

from __future__ import annotations

from collections.abc import Mapping

from selffork_orchestrator.runtime.base import LLMRuntime
from selffork_orchestrator.runtime.llama_cpp import LlamaCppServerRuntime
from selffork_orchestrator.runtime.mlx_server import MlxServerRuntime
from selffork_orchestrator.runtime.ollama import OllamaRuntime
from selffork_orchestrator.runtime.vllm import VllmRuntime
from selffork_shared.config import RuntimeConfig

__all__ = ["build_runtime"]

_BACKENDS: Mapping[str, type[LLMRuntime]] = {
    "mlx-server": MlxServerRuntime,
    "ollama": OllamaRuntime,
    "llama-cpp": LlamaCppServerRuntime,
    "vllm": VllmRuntime,
}


def build_runtime(config: RuntimeConfig) -> LLMRuntime:
    """Return a fresh :class:`LLMRuntime` instance for ``config.backend``.

    Stubbed backends (Ollama, llama-cpp, vllm in MVP v0) raise
    :class:`NotImplementedError` from their constructor, which this
    function propagates unchanged.
    """
    cls = _BACKENDS.get(config.backend)
    if cls is None:
        # Unreachable: ``config.backend`` is a Pydantic Literal validated
        # at boot. Guarded anyway so a future backend addition without a
        # matching stub fails loudly instead of silently.
        raise ValueError(f"unknown runtime backend: {config.backend!r}")
    return cls(config)
