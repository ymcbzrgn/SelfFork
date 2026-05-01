"""Unit tests for :class:`MlxServerRuntime` that don't require real mlx-lm.

Real-runtime integration tests live under
``tests/e2e/`` and are gated by ``@pytest.mark.real_runtime``.
"""

from __future__ import annotations

import pytest

from selffork_orchestrator.runtime.mlx_server import MlxServerRuntime
from selffork_shared.config import RuntimeConfig
from selffork_shared.errors import RuntimeStartError


def test_init_validates_backend() -> None:
    cfg = RuntimeConfig(backend="ollama")
    with pytest.raises(ValueError, match="mlx-server"):
        MlxServerRuntime(cfg)


def test_model_id_available_pre_start() -> None:
    cfg = RuntimeConfig()
    rt = MlxServerRuntime(cfg)
    assert rt.model_id == cfg.model_id


def test_base_url_before_start_raises() -> None:
    cfg = RuntimeConfig()
    rt = MlxServerRuntime(cfg)
    with pytest.raises(RuntimeStartError, match="before start"):
        _ = rt.base_url


@pytest.mark.asyncio
async def test_health_before_start_returns_false() -> None:
    cfg = RuntimeConfig()
    rt = MlxServerRuntime(cfg)
    assert await rt.health() is False


@pytest.mark.asyncio
async def test_stop_before_start_is_noop() -> None:
    cfg = RuntimeConfig()
    rt = MlxServerRuntime(cfg)
    # Should not raise.
    await rt.stop()
    assert await rt.health() is False
