"""VllmRuntime — planned stub.

Implementation lands in **M2+** per ADR-001 §15 (heavy-GPU runtime path).
"""

from __future__ import annotations

from collections.abc import Sequence

from selffork_orchestrator.runtime.base import ChatMessage, LLMRuntime
from selffork_shared.config import RuntimeConfig

__all__ = ["VllmRuntime"]


class VllmRuntime(LLMRuntime):
    """Stub. Not implemented in MVP v0."""

    def __init__(self, config: RuntimeConfig) -> None:
        raise NotImplementedError(
            "VllmRuntime is planned for M2+. See ADR-001 §15. "
            "For MVP, set runtime.backend='mlx-server'.",
        )

    async def start(self) -> None:  # pragma: no cover
        raise NotImplementedError

    async def stop(self) -> None:  # pragma: no cover
        raise NotImplementedError

    @property
    def base_url(self) -> str:  # pragma: no cover
        raise NotImplementedError

    @property
    def model_id(self) -> str:  # pragma: no cover
        raise NotImplementedError

    async def health(self) -> bool:  # pragma: no cover
        raise NotImplementedError

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:  # pragma: no cover
        raise NotImplementedError
