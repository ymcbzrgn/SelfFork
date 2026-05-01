"""ABC contract tests for :class:`CLIAgent`."""

from __future__ import annotations

import pytest

from selffork_orchestrator.cli_agent.base import CLIAgent


def test_cannot_instantiate_abstract() -> None:
    with pytest.raises(TypeError):
        CLIAgent()  # type: ignore[abstract, call-arg]
