"""Tests for :class:`MlxVlmAdapter` and :class:`OllamaVisionAdapter`.

Covers the M5+ surface added in commit-after-7c10b59:

* ``from_config`` field mapping.
* ``list_models`` HTTP probe — success + non-2xx + connection refused.
* Audit traceability — ``VisionOrchestrator`` emits ``model_id`` + ``backend``
  in ``body.vision.query`` payload, both via direct ``__init__`` and via
  ``from_config()``.
* Env-var override roundtrip through :func:`selffork_shared.config.load_settings`.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import httpx
import pytest

from selffork_body.vision.runtime import (
    MlxVlmAdapter,
    OllamaVisionAdapter,
    VisionOrchestrator,
)
from selffork_shared.config import VisionConfig, load_settings


def _vision_config(**overrides: Any) -> VisionConfig:
    base = VisionConfig()
    return base.model_copy(update=overrides)


# ── from_config mapping ────────────────────────────────────────────────────


def test_mlx_from_config_maps_server_url_and_model_id() -> None:
    cfg = _vision_config(
        mlx_model_id="custom/mlx-gemma",
        mlx_server_url="http://10.0.0.5:9090/",
    )
    adapter = MlxVlmAdapter.from_config(cfg)
    assert adapter.server_url == "http://10.0.0.5:9090"  # trailing slash stripped
    assert adapter.model_id == "custom/mlx-gemma"


def test_ollama_from_config_maps_host_and_model_tag() -> None:
    cfg = _vision_config(
        ollama_host="http://10.0.0.6:11434/",
        ollama_model_tag="gemma4:e4b-q4_K_M",
    )
    adapter = OllamaVisionAdapter.from_config(cfg)
    assert adapter.host == "http://10.0.0.6:11434"
    assert adapter.model == "gemma4:e4b-q4_K_M"


# ── list_models HTTP probes (mocked) ───────────────────────────────────────


def _httpx_mock(handler) -> httpx.MockTransport:  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_mlx_list_models_parses_openai_compat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(
            200,
            json={"data": [
                {"id": "mlx-community/gemma-4-E2B-it-4bit"},
                {"id": "mlx-community/gemma-4-E4B-it-4bit"},
                {"no_id": "skipped"},
            ]},
        )

    # Patch httpx.AsyncClient to use the mock transport.
    real_async_client = httpx.AsyncClient

    def patched_async_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real_async_client(transport=_httpx_mock(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_async_client)

    adapter = MlxVlmAdapter(server_url="http://x:8080")
    models = await adapter.list_models()
    assert models == [
        "mlx-community/gemma-4-E2B-it-4bit",
        "mlx-community/gemma-4-E4B-it-4bit",
    ]


@pytest.mark.asyncio
async def test_mlx_list_models_propagates_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *_a, **kw: real_async_client(transport=_httpx_mock(handler), **kw),
    )

    adapter = MlxVlmAdapter(server_url="http://x:8080")
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.list_models()


@pytest.mark.asyncio
async def test_ollama_list_models_parses_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={"models": [
                {"name": "gemma4:e2b-q4_K_M"},
                {"name": "gemma4:e4b-q4_K_M"},
                {"weird": "skipped"},
            ]},
        )

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *_a, **kw: real_async_client(transport=_httpx_mock(handler), **kw),
    )

    adapter = OllamaVisionAdapter(host="http://x:11434")
    models = await adapter.list_models()
    assert models == ["gemma4:e2b-q4_K_M", "gemma4:e4b-q4_K_M"]


@pytest.mark.asyncio
async def test_ollama_list_models_connection_refused_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *_a, **kw: real_async_client(transport=_httpx_mock(handler), **kw),
    )

    adapter = OllamaVisionAdapter(host="http://x:11434")
    with pytest.raises(httpx.ConnectError):
        await adapter.list_models()


# ── Audit traceability — VisionOrchestrator payload tagging ───────────────


class _StubRuntime:
    """Minimal MultimodalLLMRuntime that returns canned JSON decisions."""

    model_id = "stub-model"

    def __init__(self, response: dict) -> None:
        self._response = response

    async def invoke_with_images(
        self,
        messages: list[dict],
        images: Sequence[bytes],
        max_tokens: int = 256,
        temperature: float = 0.0,
        stop: Sequence[str] | None = None,
    ) -> str:
        del messages, images, max_tokens, temperature, stop
        return json.dumps(self._response)


@pytest.mark.asyncio
async def test_orchestrator_emits_model_id_and_backend_via_init() -> None:
    runtime = _StubRuntime({
        "action": "click",
        "target": "Sign in",
        "bbox": [10, 20, 80, 32],
        "args": {},
        "confidence": 0.91,
        "reason": "high-confidence top-right button",
    })
    events: list[tuple[str, dict]] = []
    orch = VisionOrchestrator(
        runtime=runtime,
        audit_emit=lambda c, p: events.append((c, p)),
        model_id="custom/swap",
        backend="mlx",
    )
    await orch.decide(screenshot=b"\x00", goal="sign in")
    assert events, "audit_emit was not called"
    category, payload = events[0]
    assert category == "body.vision.query"
    assert payload["model_id"] == "custom/swap"
    assert payload["backend"] == "mlx"
    assert payload["action"] == "click"


@pytest.mark.asyncio
async def test_orchestrator_backend_inferred_from_runtime_classname() -> None:
    """When ``backend=None``, infer from runtime class name (mlx | ollama)."""
    # Custom class names so the heuristic kicks in.

    class FakeMlxRuntime(_StubRuntime):
        pass

    runtime = FakeMlxRuntime({
        "action": "wait",
        "target": "loading spinner",
        "bbox": None,
        "args": {},
        "confidence": 0.5,
        "reason": "",
    })
    events: list[tuple[str, dict]] = []
    orch = VisionOrchestrator(
        runtime=runtime,
        audit_emit=lambda c, p: events.append((c, p)),
    )
    await orch.decide(screenshot=b"\x00", goal="wait")
    assert events[0][1]["backend"] == "mlx"
    # model_id auto-picked from runtime attribute fallback chain.
    assert events[0][1]["model_id"] == "stub-model"


@pytest.mark.asyncio
async def test_orchestrator_from_config_uses_mlx_defaults() -> None:
    """Smoke: from_config wires VisionConfig → MlxVlmAdapter + backend tag.

    We only assert the wiring properties; no HTTP probe is performed.
    """
    cfg = _vision_config(mlx_model_id="org/x", mlx_server_url="http://h:8080")
    orch = VisionOrchestrator.from_config(cfg, adapter="mlx")
    assert orch.backend == "mlx"
    assert orch.model_id == "org/x"
    assert isinstance(orch.runtime, MlxVlmAdapter)
    assert orch.runtime.model_id == "org/x"


def test_orchestrator_from_config_rejects_unknown_adapter() -> None:
    cfg = _vision_config()
    with pytest.raises(ValueError, match="unknown adapter"):
        VisionOrchestrator.from_config(cfg, adapter="not-a-thing")


# ── VisionConfig env override roundtrip ────────────────────────────────────


def test_env_override_visible_via_load_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SELFFORK_VISION__MLX_MODEL_ID`` should win over defaults."""
    monkeypatch.setenv("SELFFORK_VISION__MLX_MODEL_ID", "env-override/gemma")
    monkeypatch.setenv("SELFFORK_VISION__OLLAMA_MODEL_TAG", "gemma4:e4b-q4_K_M")
    settings = load_settings()
    assert settings.vision.mlx_model_id == "env-override/gemma"
    assert settings.vision.ollama_model_tag == "gemma4:e4b-q4_K_M"
    # Unchanged fields keep VisionConfig defaults.
    assert settings.vision.mlx_server_url == "http://127.0.0.1:8080"
