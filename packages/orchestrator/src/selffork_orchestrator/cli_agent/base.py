"""CLIAgent ABC — adapter contract for an external CLI coding agent.

A :class:`CLIAgent` knows how to drive **one** CLI coding agent (opencode,
claude-code, codex, gemini-cli) **as a user**. SelfFork's role is bridging
between SelfFork Jr (the local LLM, user simulator) and the CLI agent (which
uses its OWN powerful provider — Claude / GPT / Gemini per user config).

Per ``project_selffork_jr_is_user_simulator.md``, the SelfFork orchestrator
runs a **round loop**:

    Round 0:  history = compose_initial_messages(PRD)
              yamac_msg_0 = LLMRuntime.chat(history)
              opencode_output_0 = sandbox.exec(build_command(yamac_msg_0, first=True))
              history.append(assistant=yamac_msg_0, user=opencode_output_0)

    Round n:  yamac_msg_n = LLMRuntime.chat(history)
              if is_selffork_jr_done(yamac_msg_n): stop
              opencode_output_n = sandbox.exec(build_command(yamac_msg_n, first=False))
              history.append(...)

The CLIAgent is stateless beyond its config — same instance can drive
multiple sessions sequentially (sessions live in the underlying CLI's
state, not in the agent adapter).

See: ``docs/decisions/ADR-001_MVP_v0.md`` §5.3 (rewritten for round loop
on 2026-05-01) and ``project_selffork_jr_drives_3_cli_agents.md``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

from selffork_orchestrator.runtime.base import ChatMessage
from selffork_shared.config import CLIAgentConfig

__all__ = ["CLIAgent"]


class CLIAgent(ABC):
    """Adapter for one CLI coding agent."""

    @abstractmethod
    def __init__(self, config: CLIAgentConfig) -> None:
        """Initialise from config. Implementations must validate that
        ``config.agent`` matches this implementation, and raise
        :class:`ValueError` otherwise.
        """

    @abstractmethod
    def resolve_binary(self) -> str:
        """Locate the agent binary on disk; return absolute path.

        Raises:
            selffork_shared.errors.AgentBinaryNotFoundError: with an
                install hint when the binary cannot be located.
        """

    @abstractmethod
    def compose_initial_messages(
        self,
        *,
        prd: str,
        plan_path: str,
        workspace: str,
    ) -> list[ChatMessage]:
        """Build the initial SelfFork-Jr chat history (system + user(PRD)).

        These messages prime SelfFork Jr to write the **first** message it
        will send into the CLI agent. Round 0's user content typically
        contains the full PRD plus a pointer to the plan-as-state file.
        """

    @abstractmethod
    def build_command(self, *, message: str, is_first_round: bool) -> list[str]:
        """Build the CLI command (args after the binary) for one round.

        First round: a fresh CLI invocation (e.g. ``run "msg"``).
        Subsequent rounds: a continuation (e.g. ``run --continue "msg"``).

        The orchestrator prepends the resolved binary, runs via Sandbox,
        captures stdout, and feeds the captured text back to SelfFork Jr as
        the next user-role message.
        """

    @abstractmethod
    def build_env(self, base_env: Mapping[str, str]) -> dict[str, str]:
        """Env vars for the CLI subprocess.

        Pass-through with optional additions. **MUST NOT** redirect the
        CLI agent's LLM endpoint — each CLI uses its own provider config
        (e.g. opencode reads ``opencode.json``, claude-code reads
        ``ANTHROPIC_API_KEY``). SelfFork's local Gemma is for SelfFork Jr,
        not for these tools.
        """

    @abstractmethod
    def is_selffork_jr_done(self, reply: str) -> bool:
        """Detect a 'done' signal in SelfFork Jr's reply text.

        Returns ``True`` if the reply matches a configured done pattern
        ("tamam, bitti", "/done", etc.). The orchestrator stops the round
        loop without invoking the CLI again when this returns True.
        """
