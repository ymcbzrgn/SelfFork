"""Speaker client — the model endpoint Talk asks for Self Jr's replies.

S1 Talk Loop: the operator talks to Self Jr (the Speaker); Self Jr's
replies come from an OpenAI-compatible ``/chat/completions`` endpoint the
operator runs themselves (ADR-007 §4 S1 — §14 decision: a stock Gemma 4
E2B served by MLX-server or Ollama on the operator's Mac). SelfFork never
spawns the model — it only connects to a configurable endpoint URL, so
the operator's machine is never loaded by SelfFork itself.

Both MLX-server and Ollama expose ``POST /v1/chat/completions`` in the
OpenAI-compatible schema, so one client covers both.

**Streaming (ADR-011 — S-Stream).** The operator's target deployment is
**CPU**, where a single generation can take minutes-to-hours. A blocking
POST that holds the HTTP request for the entire generation invariably
trips httpx/proxy/browser timeouts long before the reply is ready and
gives the operator no progress / no cancel. To make slow generation
*survivable* (not hidden), the Speaker exposes a streaming variant via
the OpenAI ``stream: true`` SSE protocol. The wire vocabulary
(:class:`TokenChunk` / :class:`StreamDone`) + the idle-token watchdog +
the SSE parse loop live in :mod:`selffork_orchestrator.runtime.sse` and
are shared verbatim with the round-loop's ``MlxServerRuntime`` so both
inference seams speak one contract:

* :meth:`SpeakerClient.reply_stream` yields :class:`TokenChunk` as tokens
  arrive (the operator sees liveness even on hours-long replies),
  finalised by a single :class:`StreamDone` carrying the full aggregated
  reply + finish reason.
* An **idle-token watchdog** (``stall_seconds=``) distinguishes "slow but
  alive" (tokens still trickling) from "wedged" (no token for X seconds):
  the latter raises :class:`SpeakerStalledError` so the system can declare
  the model misconfigured *without* falsely cancelling a valid slow run.
* A **split timeout** replaces the single fixed read timeout: short
  ``connect_seconds`` (detect a down endpoint fast) + ``read=None`` (the
  idle watchdog handles per-token liveness instead of a wall-clock cap).
* :meth:`SpeakerClient.reply` is preserved for non-streaming callers and
  is now a thin wrapper that aggregates :meth:`reply_stream`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Final, Protocol

import httpx

from selffork_orchestrator.runtime.sse import (
    StreamDone,
    StreamEvent,
    TokenChunk,
    stream_openai_sse,
)
from selffork_shared.errors import RuntimeUnhealthyError

# Re-export the shared streaming vocabulary so existing callers
# (``talk_router``, tests) keep importing it from ``talk.speaker``.
__all__ = [
    "Speaker",
    "SpeakerClient",
    "StreamDone",
    "StreamEvent",
    "TokenChunk",
]


class _Unset:
    """Singleton sentinel — `stall_seconds` was not explicitly passed.

    Lets :meth:`SpeakerClient.reply_stream` distinguish "caller omitted
    the parameter (use the constructor default)" from "caller explicitly
    set ``stall_seconds=None`` (disable the watchdog)". A regular default
    of ``None`` would collapse those two cases.
    """


_UNSET: Final[_Unset] = _Unset()

# Output cap. Generous because a thinking model (e.g. stock Gemma 4 E2B)
# spends tokens on a reasoning pass before the visible reply — too low a
# cap and `content` comes back empty.
_DEFAULT_MAX_TOKENS = 2048

# ADR-011 §3.3 split timeout — connect is short (detect a dead endpoint
# fast); read is intentionally unbounded for the streaming variant and
# guarded instead by the per-token idle watchdog.
_DEFAULT_CONNECT_SECONDS = 5.0

# ADR-011 §3.3 default idle-token watchdog. ``None`` disables it
# (operator opt-out for genuinely-unbounded debugging); a positive value
# enforces "tokens must trickle this often or we call it wedged". The
# default is generous because warming the model can absorb the first
# tens of seconds; tune per-deployment as needed.
_DEFAULT_STALL_SECONDS: float | None = 90.0


class Speaker(Protocol):
    """Anything that can produce a Self Jr reply for a message history."""

    async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
        """Return Self Jr's reply for an OpenAI-shaped message list.

        Non-streaming back-compat surface. Equivalent to draining
        :meth:`reply_stream` and returning the final ``full_reply``.

        Raises:
            selffork_shared.errors.RuntimeUnhealthyError: the endpoint is
                unreachable, returned non-200, or sent a malformed body.
        """
        ...

    def reply_stream(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        stall_seconds: float | None = ...,
    ) -> AsyncIterator[StreamEvent]:
        """Stream the Self Jr reply token-by-token (ADR-011 §3).

        Yields one :class:`TokenChunk` per server-side SSE frame, and
        finalises with exactly one :class:`StreamDone` carrying the
        aggregated reply + finish reason. The caller may abandon the
        iterator at any point to cancel the upstream generation (the
        underlying httpx stream is closed and the server sees the client
        disconnect).

        Args:
            messages: OpenAI-shaped chat history.
            stall_seconds: Idle-token watchdog window. ``None`` disables
                the watchdog (run forever as long as the TCP connection
                stays alive). A positive value raises
                :class:`SpeakerStalledError` if no token arrives within
                that many seconds — used to detect a wedged model
                (e.g. ``mlx_lm`` on a VLM weight set) without falsely
                killing a legitimate slow CPU generation.

        Raises:
            selffork_shared.errors.RuntimeUnhealthyError: the endpoint is
                unreachable, returned non-200, or sent a malformed body.
            selffork_shared.errors.SpeakerStalledError: no token arrived
                within ``stall_seconds``.
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
        connect_seconds: float = _DEFAULT_CONNECT_SECONDS,
        default_stall_seconds: float | None = _DEFAULT_STALL_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_tokens = max_tokens
        self._connect_seconds = connect_seconds
        self._default_stall_seconds = default_stall_seconds
        self._transport = transport

    @property
    def model(self) -> str:
        return self._model

    @property
    def endpoint(self) -> str:
        """The OpenAI-compatible chat-completions URL."""
        return f"{self._base_url}/chat/completions"

    @property
    def default_stall_seconds(self) -> float | None:
        """Configured idle-token watchdog default (see :meth:`reply_stream`)."""
        return self._default_stall_seconds

    async def reply(self, messages: Sequence[Mapping[str, str]]) -> str:
        """Non-streaming reply (ADR-011 back-compat).

        Implemented as a drain of :meth:`reply_stream` so the wire
        protocol and parsing live in one place. ``stall_seconds`` here
        is taken from ``default_stall_seconds`` because the surface
        offers no per-call knob.
        """
        chunks: list[str] = []
        full_reply: str | None = None
        async for ev in self.reply_stream(
            messages, stall_seconds=self._default_stall_seconds
        ):
            if isinstance(ev, TokenChunk):
                chunks.append(ev.text)
                continue
            full_reply = ev.full_reply
        if full_reply is None:
            full_reply = "".join(chunks)
        return full_reply

    async def reply_stream(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        stall_seconds: float | None | _Unset = _UNSET,
    ) -> AsyncIterator[StreamEvent]:
        """Stream tokens from the Speaker (see :class:`Speaker`).

        When ``stall_seconds`` is omitted, the constructor's
        ``default_stall_seconds`` is used. Pass ``stall_seconds=None``
        explicitly to disable the idle watchdog for this call.
        """
        effective_stall: float | None
        if isinstance(stall_seconds, _Unset):
            effective_stall = self._default_stall_seconds
        else:
            effective_stall = stall_seconds
        body: dict[str, object] = {
            "model": self._model,
            "messages": [dict(m) for m in messages],
            "stream": True,
            "max_tokens": self._max_tokens,
        }
        # Connect is short (fail-fast on a dead endpoint); read is
        # intentionally unbounded — per-token liveness is enforced by
        # the idle watchdog rather than a wall-clock read cap.
        timeout = httpx.Timeout(
            connect=self._connect_seconds,
            read=None,
            write=self._connect_seconds,
            pool=self._connect_seconds,
        )
        try:
            async with httpx.AsyncClient(
                timeout=timeout, transport=self._transport
            ) as client, client.stream(
                "POST", self.endpoint, json=body
            ) as resp:
                if resp.status_code != 200:
                    body_bytes = await resp.aread()
                    raise RuntimeUnhealthyError(
                        f"speaker HTTP {resp.status_code}: "
                        f"{body_bytes.decode('utf-8', errors='replace')[:500]}"
                    )
                async for event in stream_openai_sse(
                    resp, stall_seconds=effective_stall
                ):
                    yield event
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
            raise RuntimeUnhealthyError(
                f"speaker request failed: {type(exc).__name__}: {exc}",
            ) from exc
