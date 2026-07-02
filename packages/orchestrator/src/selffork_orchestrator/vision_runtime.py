"""Prompt-shaped vision runtime for the in-round-loop intelligent tools.

The browser intelligent tools
(:mod:`selffork_orchestrator.tools.browser.intelligent`) and the VisionPro
OCR tool (:mod:`selffork_orchestrator.tools.vr.visionpro`) call a duck-typed
``await ctx.vision_runtime.decide(prompt=<str>, image=<bytes | None>)`` and
stringify the result. That is a deliberately simpler contract than the tiered
body-vision loop (:meth:`selffork_body.vision.runtime.VisionOrchestrator.decide`,
which takes ``(screenshot, goal, ...)`` and drives the driver control loop) —
so this thin runtime adapts a multimodal adapter (``MlxVlmAdapter`` /
``OllamaVisionAdapter``) to exactly the ``(prompt, image)`` shape the tools
expect.

Built (opt-in) by :func:`build_default_vision_runtime` from
:class:`selffork_shared.config.VisionConfig` and injected into the round-loop
``Session`` by ``cli.py::run``. When ``vision.enabled`` is false the factory
returns ``None`` and the intelligent tools keep returning ``unwired``.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any, Protocol

from selffork_body.vision import MlxVlmAdapter, OllamaVisionAdapter

if TYPE_CHECKING:
    from collections.abc import Sequence

    from selffork_shared.config import VisionConfig

__all__ = ["PromptVisionRuntime", "build_default_vision_runtime"]

# 1x1 transparent PNG. The wrapped adapters require exactly one image per
# request (``invoke_with_images`` raises ``ValueError`` on zero or many); the
# text-only tool paths (``browser_extract`` passes ``image=None``) send this
# placeholder so the HTTP multimodal schema stays valid without a real
# screenshot. Decoded once at import; starts with the PNG signature.
_BLANK_PNG_1X1: bytes = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAA"
    "C0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class _MultimodalAdapter(Protocol):
    """Structural type for the wrapped adapter.

    Mirrors the concrete ``MlxVlmAdapter`` / ``OllamaVisionAdapter``
    ``invoke_with_images`` signature so both the real adapters and test stubs
    satisfy it without this module depending on the concrete classes for
    typing.
    """

    async def invoke_with_images(
        self,
        messages: Sequence[dict[str, Any]],
        images: Sequence[bytes],
        max_tokens: int = ...,
        temperature: float = ...,
        stop: Sequence[str] | None = ...,
    ) -> str: ...


class PromptVisionRuntime:
    """Adapts a multimodal adapter to the tools' ``decide(prompt, image)`` contract.

    Stateless: the wrapped adapter opens a short-lived HTTP client per call,
    so no ``start``/``stop`` lifecycle is needed. A raise from the underlying
    adapter (server down, HTTP error) propagates to the caller, where the
    intelligent tools' ``_invoke_*`` wrapper records it as a tool error.
    """

    def __init__(self, adapter: _MultimodalAdapter, *, max_tokens: int = 512) -> None:
        self._adapter = adapter
        self._max_tokens = max_tokens

    async def decide(self, *, prompt: str, image: bytes | None) -> str:
        """Single multimodal turn: ``prompt`` (+ optional screenshot) → text.

        ``image=None`` (text-only extraction) sends the 1x1 placeholder so the
        adapter's single-image requirement is satisfied.
        """
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        png = image if image is not None else _BLANK_PNG_1X1
        return await self._adapter.invoke_with_images(
            messages, [png], max_tokens=self._max_tokens
        )


def build_default_vision_runtime(
    config: VisionConfig,
) -> PromptVisionRuntime | None:
    """Build the round-loop vision runtime from config, or ``None`` if disabled.

    Opt-in via ``config.enabled`` (default false → ``None``, tools stay
    ``unwired``). ``config.adapter`` selects the Tier-1 backend: ``mlx``
    (``mlx_server_url``) or ``ollama`` (``ollama_host``).
    """
    if not config.enabled:
        return None
    adapter: _MultimodalAdapter
    if config.adapter == "mlx":
        adapter = MlxVlmAdapter.from_config(config)
    else:
        adapter = OllamaVisionAdapter.from_config(config)
    return PromptVisionRuntime(adapter)
