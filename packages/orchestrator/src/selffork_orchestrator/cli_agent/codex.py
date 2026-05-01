"""CodexAgent — planned stub.

Implementation lands in **M2-M3** per
``project_selffork_jr_drives_3_cli_agents.md``.
"""

from __future__ import annotations

from collections.abc import Mapping

from selffork_orchestrator.cli_agent.base import CLIAgent
from selffork_orchestrator.runtime.base import ChatMessage
from selffork_shared.config import CLIAgentConfig

__all__ = ["CodexAgent"]


class CodexAgent(CLIAgent):
    """Stub. Not implemented in MVP v0."""

    def __init__(self, config: CLIAgentConfig) -> None:
        raise NotImplementedError(
            "CodexAgent is planned for M2-M3. For MVP, set cli_agent.agent='opencode'.",
        )

    def resolve_binary(self) -> str:  # pragma: no cover
        raise NotImplementedError

    def compose_initial_messages(
        self,
        *,
        prd: str,
        plan_path: str,
        workspace: str,
    ) -> list[ChatMessage]:  # pragma: no cover
        raise NotImplementedError

    def build_command(
        self,
        *,
        message: str,
        is_first_round: bool,
    ) -> list[str]:  # pragma: no cover
        raise NotImplementedError

    def build_env(self, base_env: Mapping[str, str]) -> dict[str, str]:  # pragma: no cover
        raise NotImplementedError

    def is_selffork_jr_done(self, reply: str) -> bool:  # pragma: no cover
        raise NotImplementedError
