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
from selffork_shared.config import VisionConfig

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

    The model itself is loaded by the external ``mlx_vlm.server --model <id>``
    process; this adapter only talks HTTP. ``model_id`` is metadata used by
    the audit log and the Cockpit Settings → Vision dropdown.
    """

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8080",
        *,
        model_id: str = "mlx-community/gemma-4-E2B-it-4bit",
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.model_id = model_id

    @classmethod
    def from_config(cls, config: VisionConfig) -> "MlxVlmAdapter":  # noqa: UP037
        """Build adapter from :class:`selffork_shared.config.VisionConfig`."""
        return cls(server_url=config.mlx_server_url, model_id=config.mlx_model_id)

    async def list_models(self) -> list[str]:
        """Probe ``GET /v1/models`` (OpenAI-compat) for available IDs.

        Raises ``httpx.HTTPError`` subclasses on network / non-2xx response so
        the caller (Cockpit auto-detect endpoint) can map them to user-facing
        error messages.
        """
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{self.server_url}/v1/models")
            r.raise_for_status()
            data = r.json().get("data", [])
            return [m["id"] for m in data if isinstance(m, dict) and "id" in m]

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

    def __init__(self, host: str = "http://127.0.0.1:11434", model: str = "gemma4:e2b-q4_K_M") -> None:
        self.host = host.rstrip("/")
        self.model = model

    @classmethod
    def from_config(cls, config: VisionConfig) -> "OllamaVisionAdapter":  # noqa: UP037
        """Build adapter from :class:`selffork_shared.config.VisionConfig`."""
        return cls(host=config.ollama_host, model=config.ollama_model_tag)

    async def list_models(self) -> list[str]:
        """Probe ``GET /api/tags`` for available Ollama model tags.

        Raises ``httpx.HTTPError`` subclasses; caller maps to user-facing
        error.
        """
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{self.host}/api/tags")
            r.raise_for_status()
            models = r.json().get("models", [])
            return [m["name"] for m in models if isinstance(m, dict) and "name" in m]

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
        model_id: str | None = None,
        backend: str | None = None,
    ) -> None:
        self.runtime = runtime
        self.tier1_threshold = tier1_threshold
        self.tier2_threshold = tier2_threshold
        self.audit_emit = audit_emit
        self.clock = clock or time.monotonic
        # Audit traceability — UI-TARS AGIO pattern. When the orchestrator
        # is built via ``VisionOrchestrator.from_config(...)``, both fields
        # are populated automatically; legacy callers default to None which
        # emits as ``"unknown"`` in the audit payload.
        if model_id is None:
            model_id = getattr(runtime, "model_id", None) or getattr(
                runtime, "model", None,
            )
        if backend is None:
            # Heuristic: class name → backend tag (mlx | ollama | other).
            cls = type(runtime).__name__.lower()
            if "mlx" in cls:
                backend = "mlx"
            elif "ollama" in cls:
                backend = "ollama"
        self.model_id = model_id
        self.backend = backend

    @classmethod
    def from_config(
        cls,
        config: VisionConfig,
        *,
        adapter: str = "mlx",
        audit_emit=None,  # type: ignore[no-untyped-def]
    ) -> "VisionOrchestrator":  # noqa: UP037
        """Build orchestrator from :class:`VisionConfig` with traceability tagged.

        ``adapter`` selects the Tier-1 runtime: ``"mlx"`` (Apple Silicon
        default) or ``"ollama"`` (Linux fallback).
        """
        if adapter == "mlx":
            runtime: MlxVlmAdapter | OllamaVisionAdapter = MlxVlmAdapter.from_config(config)
            model_id, backend = config.mlx_model_id, "mlx"
        elif adapter == "ollama":
            runtime = OllamaVisionAdapter.from_config(config)
            model_id, backend = config.ollama_model_tag, "ollama"
        else:
            raise ValueError(f"unknown adapter: {adapter!r} (expected mlx|ollama)")
        return cls(
            runtime=runtime,
            audit_emit=audit_emit,
            model_id=model_id,
            backend=backend,
        )

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
                    "model_id": self.model_id or "unknown",
                    "backend": self.backend or "unknown",
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
