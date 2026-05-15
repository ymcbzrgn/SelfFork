"""Vision runtime adapters and the Tier-1/2/3 orchestrator.

Adapters bridge :class:`MultimodalLLMRuntime` Protocol (defined in
``selffork_orchestrator.runtime.base``) to concrete backends:

* :class:`MlxVlmAdapter` — Apple Silicon, talks to ``mlx_vlm.server``.
* :class:`OllamaVisionAdapter` — Linux fallback, talks to Ollama HTTP API.

The orchestrator coordinates Tier-1 → Tier-2 → Tier-3 fallback and emits
``body.vision.query`` audit events.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from selffork_body.vision.prompt import Tier, build_prompt, parse_decision

__all__ = [
    "MlxVlmAdapter",
    "OllamaVisionAdapter",
    "VisionDecision",
    "VisionOrchestrator",
]


@dataclass(frozen=True, slots=True)
class VisionDecision:
    action: str
    target: str
    bbox: tuple[int, int, int, int] | None
    args: dict
    confidence: float
    reason: str
    tier: Tier
    duration_ms: int


def _decision_from_dict(payload: dict, *, tier: Tier, duration_ms: int) -> VisionDecision:
    bbox_raw = payload.get("bbox")
    bbox: tuple[int, int, int, int] | None = None
    if isinstance(bbox_raw, (list, tuple)) and len(bbox_raw) == 4:
        bbox = tuple(int(v) for v in bbox_raw)  # type: ignore[assignment]
    return VisionDecision(
        action=str(payload["action"]),
        target=str(payload.get("target", "")),
        bbox=bbox,
        args=dict(payload.get("args") or {}),
        confidence=float(payload.get("confidence", 0.0)),
        reason=str(payload.get("reason", "")),
        tier=tier,
        duration_ms=duration_ms,
    )


class MlxVlmAdapter:
    """Adapter wrapping ``mlx_vlm.server`` HTTP endpoint (Apple Silicon).

    Compatible with the OpenAI chat-completions schema. Sends image as
    ``image_url`` with ``data:image/png;base64,…`` payload.
    """

    def __init__(self, server_url: str = "http://127.0.0.1:8080") -> None:
        self.server_url = server_url.rstrip("/")

    async def invoke_with_images(
        self,
        messages,  # type: ignore[no-untyped-def]
        images: Sequence[bytes],
        max_tokens: int = 256,
        temperature: float = 0.0,
        stop: Sequence[str] | None = None,
    ) -> str:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("mlx adapter requires httpx") from exc

        if len(images) != 1:
            raise ValueError("MlxVlmAdapter currently supports a single image per request")
        image_b64 = base64.b64encode(images[0]).decode("ascii")
        # Compose openai-style multimodal content
        rendered_messages: list[dict] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str):
                rendered_messages.append(
                    {
                        "role": role,
                        "content": [
                            {"type": "text", "text": content},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                            },
                        ],
                    }
                )
            else:
                rendered_messages.append({"role": role, "content": content})
        payload = {
            "messages": rendered_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stop:
            payload["stop"] = list(stop)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.server_url}/v1/chat/completions", json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


class OllamaVisionAdapter:
    """Adapter for ``ollama serve`` HTTP API.

    Ollama accepts ``images`` as a list of base64-encoded strings on the
    chat endpoint. Linux server-side fallback when MLX is unavailable.
    """

    def __init__(self, host: str = "http://127.0.0.1:11434", model: str = "gemma3") -> None:
        self.host = host.rstrip("/")
        self.model = model

    async def invoke_with_images(
        self,
        messages,  # type: ignore[no-untyped-def]
        images: Sequence[bytes],
        max_tokens: int = 256,
        temperature: float = 0.0,
        stop: Sequence[str] | None = None,
    ) -> str:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("ollama adapter requires httpx") from exc

        rendered: list[dict] = []
        encoded_images = [base64.b64encode(img).decode("ascii") for img in images]
        for idx, msg in enumerate(messages):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            text = (
                content
                if isinstance(content, str)
                else "\n".join(part["text"] for part in content if part.get("type") == "text")
            )
            entry: dict = {"role": role, "content": text}
            if idx == len(messages) - 1 and encoded_images:
                entry["images"] = encoded_images
            rendered.append(entry)
        payload = {
            "model": self.model,
            "messages": rendered,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                "stop": list(stop) if stop else None,
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]


class VisionOrchestrator:
    """Tier-1 → Tier-2 → Tier-3 fallback coordinator.

    The runtime is anything implementing
    :class:`selffork_orchestrator.runtime.base.MultimodalLLMRuntime` (the
    in-process Protocol). Audit emit is delegated to a callback so this
    layer remains pillar-agnostic.
    """

    def __init__(
        self,
        runtime,  # type: ignore[no-untyped-def]
        *,
        tier1_threshold: float = 0.7,
        tier2_threshold: float = 0.5,
        audit_emit=None,  # type: ignore[no-untyped-def]
        clock=None,  # type: ignore[no-untyped-def]
    ) -> None:
        self.runtime = runtime
        self.tier1_threshold = tier1_threshold
        self.tier2_threshold = tier2_threshold
        self.audit_emit = audit_emit
        self.clock = clock or time.monotonic

    async def _invoke(self, prompt: str, screenshot: bytes, *, tier: Tier) -> VisionDecision:
        messages = [
            {"role": "system", "content": "You are a UI control agent."},
            {"role": "user", "content": prompt},
        ]
        started = self.clock()
        raw = await self.runtime.invoke_with_images(messages, [screenshot])
        elapsed_ms = int((self.clock() - started) * 1000)
        decision = _decision_from_dict(parse_decision(raw), tier=tier, duration_ms=elapsed_ms)
        if self.audit_emit is not None:
            self.audit_emit(
                "body.vision.query",
                {
                    "tier": tier,
                    "duration_ms": elapsed_ms,
                    "confidence": decision.confidence,
                    "action": decision.action,
                    "target": decision.target,
                    "ts": datetime.now(UTC).isoformat(),
                },
            )
        return decision

    async def decide(
        self,
        screenshot: bytes,
        goal: str,
        *,
        ax_tree_text: str | None = None,
        marks_summary: str | None = None,
    ) -> VisionDecision:
        """Run the tiered fallback, return the first acceptable decision."""
        # Tier-1
        prompt1 = build_prompt(tier=1, goal=goal)
        d1 = await self._invoke(prompt1, screenshot, tier=1)
        if d1.confidence >= self.tier1_threshold:
            return d1
        # Tier-2 — needs ax tree; if unavailable, return d1 anyway as best-effort.
        if not ax_tree_text:
            return d1
        prompt2 = build_prompt(
            tier=2, goal=goal, ax_tree_text=ax_tree_text, prev_confidence=d1.confidence
        )
        d2 = await self._invoke(prompt2, screenshot, tier=2)
        if d2.confidence >= self.tier2_threshold:
            return d2
        # Tier-3 — SoM is opt-in; require marks_summary.
        if not marks_summary:
            return d2
        prompt3 = build_prompt(
            tier=3,
            goal=goal,
            ax_tree_text=ax_tree_text,
            prev_confidence=d2.confidence,
            marks_summary=marks_summary,
        )
        return await self._invoke(prompt3, screenshot, tier=3)
