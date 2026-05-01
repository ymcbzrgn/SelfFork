"""LLMRuntime ABC — the contract every backend implements.

A runtime brings up a local LLM behind an OpenAI-compatible HTTP API on a
localhost port. The orchestrator uses :meth:`chat` to ask **SelfFork Jr**
(the local LLM, role: user-simulator per
``project_selffork_jr_is_user_simulator.md``) what message to send next to
the CLI agent (opencode / claude-code / gemini-cli — each driven by its
own powerful provider, NOT by this runtime).

Lifecycle: ``__init__(config)`` → :meth:`start` → use :meth:`chat` /
:attr:`base_url` → :meth:`stop`. Implementations must be safe to start /
stop multiple times in a process; multiple instances may coexist.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from selffork_shared.config import RuntimeConfig

__all__ = ["ChatMessage", "LLMRuntime"]

ChatMessage = dict[str, str]
"""One chat-completion message: ``{"role": "user|assistant|system", "content": "..."}``."""


class LLMRuntime(ABC):
    """Local LLM runtime exposing an OpenAI-compatible HTTP API."""

    @abstractmethod
    def __init__(self, config: RuntimeConfig) -> None:
        """Initialise from a :class:`RuntimeConfig`.

        Implementations must validate that ``config.backend`` matches the
        backend they implement, and raise :class:`ValueError` otherwise.
        """

    @abstractmethod
    async def start(self) -> None:
        """Spawn the runtime subprocess and wait for readiness.

        Polls a health endpoint until ``200 OK`` or until the configured
        startup timeout elapses.

        Raises:
            selffork_shared.errors.RuntimeStartError: subprocess failed to
                spawn or never became healthy within the timeout.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown: SIGTERM, wait grace, SIGKILL fallback.

        Idempotent — safe to call when already stopped.
        """

    @property
    @abstractmethod
    def base_url(self) -> str:
        """OpenAI-compatible base URL, e.g. ``http://127.0.0.1:8080/v1``.

        Available only between :meth:`start` and :meth:`stop`. Accessing
        outside that window raises
        :class:`selffork_shared.errors.RuntimeStartError`.
        """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Identifier for the model the runtime is serving."""

    @abstractmethod
    async def health(self) -> bool:
        """Return ``True`` iff the runtime accepts requests right now.

        Cheap probe — keep latency under ~2 seconds; never raise — return
        ``False`` on any error.
        """

    @abstractmethod
    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Run a single chat-completion turn; return the assistant text.

        Calls ``POST <base_url>/chat/completions`` with the supplied
        message list. Used by the orchestrator to ask SelfFork Jr what to
        say to the CLI agent on each round.

        Args:
            messages: ordered list of ``{"role": ..., "content": ...}``.
            max_tokens: cap on output length. ``None`` = use server default.
            temperature: sampling temperature. ``None`` = use server default.

        Returns:
            The assistant's reply text (``choices[0].message.content``).

        Raises:
            selffork_shared.errors.RuntimeUnhealthyError: HTTP error,
                non-200 response, or malformed body.
        """
