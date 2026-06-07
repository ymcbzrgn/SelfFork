"""OpenAI streaming SSE consumption — shared by Talk + the round-loop.

ADR-011 (S-Stream): both the Talk Speaker (connect-only client) and the
round-loop ``MlxServerRuntime`` (spawn-owning client) consume an
OpenAI-compatible ``/chat/completions`` stream (``stream: true``). The
wire vocabulary + the idle-token watchdog live here once so the two
call-sites share an identical contract instead of duplicating the parse
loop.

This module is the lowest layer (depends only on ``httpx`` +
``selffork_shared.errors``); ``talk.speaker`` and ``runtime.mlx_server``
both import from it (talk/runtime → this is a downward dependency, no
cycle).

Stream shape: :func:`stream_openai_sse` yields one :class:`TokenChunk`
per server SSE frame that carried ``delta.content``, then exactly one
:class:`StreamDone` carrying the aggregated reply + finish reason. The
idle-token watchdog raises :class:`~selffork_shared.errors.SpeakerStalledError`
when no token arrives within ``stall_seconds`` — distinguishing a wedged
model from one that is merely slow (the whole point on CPU deployments).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from selffork_shared.errors import RuntimeUnhealthyError, SpeakerStalledError

__all__ = [
    "StreamDone",
    "StreamEvent",
    "TokenChunk",
    "parse_sse_line",
    "stalling_aiter",
    "stream_openai_sse",
]


@dataclass(frozen=True, slots=True)
class TokenChunk:
    """One streamed token (or token group) from an OpenAI SSE stream.

    Carries whatever ``delta.content`` the server emitted in a single
    ``data:`` frame. Concatenating the ``text`` of every ``TokenChunk``
    in a stream reproduces the model's full reply (which the final
    :class:`StreamDone` also carries verbatim).
    """

    text: str


@dataclass(frozen=True, slots=True)
class StreamDone:
    """End-of-stream marker with the full aggregated reply.

    Emitted exactly once at the end of a successful stream.
    ``finish_reason`` mirrors the OpenAI ``choices[0].finish_reason``
    (``"stop"`` / ``"length"`` / model-defined / ``None``).
    """

    full_reply: str
    finish_reason: str | None


type StreamEvent = TokenChunk | StreamDone


async def stream_openai_sse(
    response: httpx.Response,
    *,
    stall_seconds: float | None,
) -> AsyncIterator[StreamEvent]:
    """Consume an already-opened streaming chat-completions response.

    The caller opens the ``httpx`` stream (``client.stream("POST", ...)``)
    and checks the status code; this consumes the body. Yields
    :class:`TokenChunk` per content frame, finalised by one
    :class:`StreamDone`.

    Raises:
        selffork_shared.errors.SpeakerStalledError: no token within
            ``stall_seconds`` (``None`` disables the watchdog).
        selffork_shared.errors.RuntimeUnhealthyError: a ``data:`` frame
            carried malformed JSON (broken wire protocol).
    """
    chunks: list[str] = []
    finish_reason: str | None = None
    async for line in stalling_aiter(response.aiter_lines(), stall_seconds=stall_seconds):
        token_text, done, frame_finish = parse_sse_line(line)
        if frame_finish is not None:
            finish_reason = frame_finish
        if token_text:
            chunks.append(token_text)
            yield TokenChunk(text=token_text)
        # Terminate on EITHER the literal ``data: [DONE]`` sentinel OR an
        # OpenAI ``finish_reason`` frame. Some servers (and proxies) send
        # the finish frame and then keep the socket open without ever
        # emitting ``[DONE]`` — without this, the idle watchdog would fire
        # ``stall_seconds`` later and mislabel an already-complete reply as
        # "wedged" (audit-god S-Stream backend finding #1).
        if done or frame_finish is not None:
            break
    yield StreamDone(full_reply="".join(chunks), finish_reason=finish_reason)


async def stalling_aiter(
    lines: AsyncIterator[str],
    *,
    stall_seconds: float | None,
) -> AsyncIterator[str]:
    """Wrap an async line iterator with an idle-token watchdog.

    Every line read is wrapped in ``asyncio.wait_for`` with
    ``stall_seconds`` as the deadline; a timeout raises
    :class:`SpeakerStalledError`. ``stall_seconds=None`` disables the
    watchdog (yield lines without a deadline).
    """
    iterator = lines.__aiter__()
    while True:
        try:
            if stall_seconds is None:
                line = await iterator.__anext__()
            else:
                line = await asyncio.wait_for(iterator.__anext__(), timeout=stall_seconds)
        except StopAsyncIteration:
            return
        except TimeoutError as exc:
            raise SpeakerStalledError(
                f"no SSE token received for {stall_seconds}s "
                "(model wedged or runtime misconfigured)"
            ) from exc
        yield line


def parse_sse_line(line: str) -> tuple[str, bool, str | None]:
    """Parse one OpenAI SSE line.

    Returns ``(token_text, done, finish_reason)``:

    * ``token_text`` — non-empty when the frame carried ``delta.content``.
    * ``done`` — ``True`` only for the literal ``data: [DONE]`` terminator.
    * ``finish_reason`` — the OpenAI ``finish_reason`` if present.

    Non-data lines (heartbeats, blank lines, ``event:`` lines) parse to
    ``("", False, None)``. Malformed JSON in a ``data:`` frame raises
    :class:`RuntimeUnhealthyError` — the wire protocol is broken.
    """
    if not line:
        return "", False, None
    if not line.startswith("data:"):
        # SSE heartbeat / event: / id: / comment lines — ignore.
        return "", False, None
    payload = line[len("data:") :].strip()
    if payload == "[DONE]":
        return "", True, None
    try:
        frame = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeUnhealthyError(f"SSE frame malformed: {exc}; payload={payload[:200]}") from exc
    if not isinstance(frame, dict):
        raise RuntimeUnhealthyError(f"SSE frame not an object: {type(frame).__name__}")
    choices = frame.get("choices")
    if not isinstance(choices, list) or not choices:
        return "", False, None
    first = choices[0]
    if not isinstance(first, dict):
        return "", False, None
    delta = first.get("delta")
    finish_reason_raw = first.get("finish_reason")
    finish_reason: str | None = finish_reason_raw if isinstance(finish_reason_raw, str) else None
    if not isinstance(delta, dict):
        return "", False, finish_reason
    content = delta.get("content")
    if not isinstance(content, str):
        return "", False, finish_reason
    return content, False, finish_reason
