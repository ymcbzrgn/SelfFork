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


# ── Shared-mode unit tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shared_mode_rejects_auto_allocate_port() -> None:
    # Shared mode means we attach to a server someone else started — we
    # MUST know the port. port=0 (auto-allocate) only makes sense when
    # we're spawning the server ourselves.
    cfg = RuntimeConfig(mode="shared", port=0)
    rt = MlxServerRuntime(cfg)
    with pytest.raises(RuntimeStartError, match="requires a concrete port"):
        await rt.start()


@pytest.mark.asyncio
async def test_shared_mode_stop_skips_process_teardown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # In shared mode the runtime never owns a subprocess; stop() must
    # NEVER reach _terminate_group regardless of internal state. Spy on
    # the group-killer to assert it stays untouched.
    cfg = RuntimeConfig(mode="shared", port=8080)
    rt = MlxServerRuntime(cfg)

    calls: list[object] = []

    async def _spy(proc: object) -> None:
        calls.append(proc)

    monkeypatch.setattr(MlxServerRuntime, "_terminate_group", staticmethod(_spy))
    await rt.stop()
    assert calls == []
    assert await rt.health() is False
