"""Tests for :func:`build_runtime`."""

from __future__ import annotations

import pytest

from selffork_orchestrator.runtime.factory import build_runtime
from selffork_orchestrator.runtime.mlx_server import MlxServerRuntime
from selffork_shared.config import RuntimeConfig


def test_mlx_server_resolved() -> None:
    cfg = RuntimeConfig(backend="mlx-server")
    rt = build_runtime(cfg)
    assert isinstance(rt, MlxServerRuntime)


@pytest.mark.parametrize("backend", ["ollama", "llama-cpp", "vllm"])
def test_stubbed_backends_raise(backend: str) -> None:
    cfg = RuntimeConfig(backend=backend)  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError):
        build_runtime(cfg)
