"""Speaker client — the model endpoint Talk asks for Self Jr's replies.

S1 Talk Loop: the operator talks to Self Jr (the Speaker); Self Jr's
replies come from an OpenAI-compatible ``/chat/completions`` endpoint the
operator runs themselves (ADR-007 §4 S1 — §14 decision: a stock Gemma 4
E2B served by MLX-server or Ollama on the operator's Mac). SelfFork never
spawns the model — it only connects to a configurable endpoint URL, so
the operator's machine is never loaded by SelfFork itself.

Both MLX-server and Ollama expose ``POST /v1/chat/completions`` in the
OpenAI-compatible schema, so one client covers both. The request/response
shape and the :class:`RuntimeUnhealthyError` failure mode mirror
:meth:`MlxServerRuntime.chat`; the talk router catches that error and
surfaces an honest "Self Jr offline" state rather than a fabricated reply
(``project_ui_stack`` no-mock rule).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

import httpx

from selffork_shared.errors import RuntimeUnhealthyError

__all__ = ["Speaker", "SpeakerClient"]

# Output cap. Generous because a thinking model (e.g. stock Gemma 4 E2B)
# spends tokens on a reasoning pass before the visible reply — too low a
# cap and `content` comes back empty. The first call after the model
# server starts is the slowest (cold load); a generous timeout absorbs it.
_DEFAULT_MAX_TOKENS = 2048
_DEFAULT_TIMEOUT_SECONDS = 120.0


class Speaker(Protocol):
    """Anything that can produce a Self Jr reply for a message history."""

    async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
        """Return Self Jr's reply for an OpenAI-shaped message list.

        Raises:
            selffork_shared.errors.RuntimeUnhealthyError: the endpoint is
                unreachable, returned non-200, or sent a malformed body.
        """
        ...


class SpeakerClient:
    """Connect-only OpenAI-compatible chat client for the Talk surface.

    ``base_url`` is the operator-managed endpoint, e.g.
    ``http://127.0.0.1:8080/v1`` (MLX-server) or
    ``http://127.0.0.1:11434/v1`` (Ollama). The client POSTs to
    ``<base_url>/chat/completions`` and never spawns or manages the model
    process. ``transport`` is an injection seam for tests
    (``httpx.MockTransport``); production leaves it ``None``.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def model(self) -> str:
        return self._model

    @property
    def endpoint(self) -> str:
        """The OpenAI-compatible chat-completions URL."""
        return f"{self._base_url}/chat/completions"

    async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
        body: dict[str, object] = {
            "model": self._model,
            "messages": [dict(m) for m in messages],
            "stream": False,
            "max_tokens": self._max_tokens,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                resp = await client.post(self.endpoint, json=body)
        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.HTTPError,
        ) as exc:
            raise RuntimeUnhealthyError(
                f"speaker request failed: {type(exc).__name__}: {exc}",
            ) from exc

        if resp.status_code != 200:
            raise RuntimeUnhealthyError(
                f"speaker HTTP {resp.status_code}: {resp.text[:500]}",
            )

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeUnhealthyError(
                f"speaker response malformed: {type(exc).__name__}: {exc}",
            ) from exc

        if not isinstance(content, str):
            raise RuntimeUnhealthyError(
                "speaker response content is not a string "
                f"(got {type(content).__name__})",
            )
        return content
