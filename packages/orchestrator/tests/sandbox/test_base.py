"""ABC contract tests for :class:`Sandbox` and :class:`SandboxProcess`."""

from __future__ import annotations

import pytest

from selffork_orchestrator.sandbox.base import Sandbox, SandboxProcess


def test_cannot_instantiate_abstract_sandbox() -> None:
    with pytest.raises(TypeError):
        Sandbox()  # type: ignore[abstract, call-arg]


def test_cannot_instantiate_abstract_process() -> None:
    with pytest.raises(TypeError):
        SandboxProcess()  # type: ignore[abstract]
