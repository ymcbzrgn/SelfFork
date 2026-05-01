"""Unit tests for :mod:`selffork_shared.errors`."""

from __future__ import annotations

import builtins

import pytest

from selffork_shared.errors import (
    AgentBinaryNotFoundError,
    AgentError,
    AgentExitError,
    AgentParseError,
    AgentSpawnError,
    AgentTimeoutError,
    ConfigError,
    PlanError,
    PlanLoadError,
    PlanSaveError,
    RuntimeError,
    RuntimeStartError,
    RuntimeUnhealthyError,
    SandboxError,
    SandboxExecError,
    SandboxSpawnError,
    SandboxTeardownError,
    SelfForkError,
    SelfForkTimeoutError,
)


class TestHierarchy:
    @pytest.mark.parametrize(
        "cls",
        [
            ConfigError,
            RuntimeError,
            SandboxError,
            AgentError,
            PlanError,
            SelfForkTimeoutError,
        ],
    )
    def test_domain_inherits_from_root(self, cls: type[Exception]) -> None:
        assert issubclass(cls, SelfForkError)

    @pytest.mark.parametrize(
        ("subclass", "umbrella"),
        [
            (RuntimeStartError, RuntimeError),
            (RuntimeUnhealthyError, RuntimeError),
            (SandboxSpawnError, SandboxError),
            (SandboxExecError, SandboxError),
            (SandboxTeardownError, SandboxError),
            (AgentBinaryNotFoundError, AgentError),
            (AgentSpawnError, AgentError),
            (AgentParseError, AgentError),
            (AgentTimeoutError, AgentError),
            (AgentExitError, AgentError),
            (PlanLoadError, PlanError),
            (PlanSaveError, PlanError),
        ],
    )
    def test_subclass_inherits_umbrella(
        self,
        subclass: type[Exception],
        umbrella: type[Exception],
    ) -> None:
        assert issubclass(subclass, umbrella)


class TestRaise:
    def test_runtime_start_caught_as_runtime(self) -> None:
        with pytest.raises(RuntimeError) as exc_info:
            raise RuntimeStartError("mlx-server failed on port 8001")
        assert "mlx-server" in str(exc_info.value)

    def test_runtime_start_caught_as_root(self) -> None:
        with pytest.raises(SelfForkError):
            raise RuntimeStartError("boom")

    def test_sandbox_subclass_caught_as_umbrella(self) -> None:
        with pytest.raises(SandboxError):
            raise SandboxExecError("exec failed")

    def test_agent_timeout_distinct_from_selffork_timeout(self) -> None:
        with pytest.raises(AgentError):
            raise AgentTimeoutError("opencode timed out")
        with pytest.raises(SelfForkTimeoutError):
            raise SelfForkTimeoutError("session timed out")
        # AgentTimeoutError is NOT a SelfForkTimeoutError
        assert not issubclass(AgentTimeoutError, SelfForkTimeoutError)


class TestRuntimeErrorShadow:
    """Our ``RuntimeError`` is intentionally distinct from Python's built-in."""

    def test_distinct_from_builtin(self) -> None:
        # mypy can prove these classes are different statically — but we
        # assert it at runtime so the shadow is documented as a contract,
        # not just a type-system observation.
        assert RuntimeError is not builtins.RuntimeError  # type: ignore[comparison-overlap]
        assert not issubclass(RuntimeError, builtins.RuntimeError)
        assert not issubclass(builtins.RuntimeError, RuntimeError)

    def test_python_runtime_error_not_caught_by_ours(self) -> None:
        # If someone raises Python's RuntimeError, our handlers must not
        # accidentally catch it.
        with pytest.raises(builtins.RuntimeError):
            _raise_builtin_runtime_error()


def _raise_builtin_runtime_error() -> None:
    """Helper: raise Python's built-in RuntimeError (not SelfFork's)."""
    raise builtins.RuntimeError("python builtin")
