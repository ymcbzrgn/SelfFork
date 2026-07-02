"""Tests for the prompt-shaped vision runtime shim + factory."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from selffork_body.vision import MlxVlmAdapter, OllamaVisionAdapter
from selffork_orchestrator.vision_runtime import (
    _BLANK_PNG_1X1,
    PromptVisionRuntime,
    build_default_vision_runtime,
)
from selffork_shared.config import VisionConfig


class _RecordingAdapter:
    """Multimodal adapter stub recording each ``invoke_with_images`` call."""

    def __init__(self, reply: str = "DECISION") -> None:
        self.reply = reply
        self.calls: list[tuple[list[dict[str, Any]], list[bytes], int]] = []

    async def invoke_with_images(
        self,
        messages: Sequence[dict[str, Any]],
        images: Sequence[bytes],
        max_tokens: int = 256,
        temperature: float = 0.0,
        stop: Sequence[str] | None = None,
    ) -> str:
        self.calls.append((list(messages), list(images), max_tokens))
        return self.reply


async def test_decide_passes_real_image_through() -> None:
    adapter = _RecordingAdapter(reply="ok-decision")
    runtime = PromptVisionRuntime(adapter, max_tokens=128)

    out = await runtime.decide(prompt="do X", image=b"REAL_PNG_BYTES")

    assert out == "ok-decision"
    messages, images, max_tokens = adapter.calls[0]
    assert images == [b"REAL_PNG_BYTES"]
    assert max_tokens == 128
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "do X"


async def test_decide_uses_placeholder_when_image_none() -> None:
    adapter = _RecordingAdapter()
    runtime = PromptVisionRuntime(adapter)

    await runtime.decide(prompt="extract fields", image=None)

    _messages, images, _max_tokens = adapter.calls[0]
    # Exactly one image (adapters reject 0 or many) — the 1x1 placeholder.
    assert images == [_BLANK_PNG_1X1]


def test_placeholder_is_a_valid_png() -> None:
    assert _BLANK_PNG_1X1.startswith(b"\x89PNG\r\n\x1a\n")


def test_factory_returns_none_when_disabled() -> None:
    assert build_default_vision_runtime(VisionConfig(enabled=False)) is None


def test_factory_builds_mlx_adapter() -> None:
    runtime = build_default_vision_runtime(VisionConfig(enabled=True, adapter="mlx"))
    assert isinstance(runtime, PromptVisionRuntime)
    assert isinstance(runtime._adapter, MlxVlmAdapter)


def test_factory_builds_ollama_adapter() -> None:
    runtime = build_default_vision_runtime(
        VisionConfig(enabled=True, adapter="ollama")
    )
    assert isinstance(runtime, PromptVisionRuntime)
    assert isinstance(runtime._adapter, OllamaVisionAdapter)
