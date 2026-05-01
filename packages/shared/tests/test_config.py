"""Unit tests for :mod:`selffork_shared.config`."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from selffork_shared.config import (
    AuditConfig,
    CLIAgentConfig,
    LifecycleConfig,
    LoggingConfig,
    PlanConfig,
    RuntimeConfig,
    SandboxConfig,
    SelfForkSettings,
    load_settings,
)
from selffork_shared.errors import ConfigError


def _clear_selffork_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wipe ``SELFFORK_*`` env vars so a test gets a clean slate."""
    for key in list(os.environ):
        if key.startswith("SELFFORK_"):
            monkeypatch.delenv(key, raising=False)


class TestSubConfigDefaults:
    def test_runtime_defaults(self) -> None:
        cfg = RuntimeConfig()
        assert cfg.backend == "mlx-server"
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8080  # mlx-lm default
        assert cfg.startup_timeout_seconds == 180
        assert cfg.health_check_interval_seconds == 2.0
        # Smallest known PLE-safe MLX 4-bit Gemma 4 E2B-it variant.
        assert "gemma-4-e2b-it" in cfg.model_id.lower()
        assert "4bit" in cfg.model_id.lower()

    def test_sandbox_defaults(self) -> None:
        cfg = SandboxConfig()
        assert cfg.mode == "subprocess"
        assert cfg.cpu_limit is None
        assert cfg.memory_limit_mb is None
        assert cfg.timeout_seconds == 3600

    def test_cli_agent_defaults(self) -> None:
        cfg = CLIAgentConfig()
        assert cfg.agent == "opencode"
        assert cfg.binary_path is None
        assert cfg.extra_args == []

    def test_plan_defaults(self) -> None:
        cfg = PlanConfig()
        assert cfg.backend == "filesystem"
        assert cfg.plan_filename == ".selffork/plan.json"

    def test_lifecycle_defaults(self) -> None:
        cfg = LifecycleConfig()
        assert cfg.skip_verify is False
        assert cfg.verifier_mode == "lenient"

    def test_logging_defaults(self) -> None:
        cfg = LoggingConfig()
        assert cfg.level == "INFO"
        assert cfg.json_output is True

    def test_audit_defaults(self) -> None:
        cfg = AuditConfig()
        assert cfg.enabled is True
        assert cfg.redact_secrets is True


class TestStrictness:
    def test_unknown_field_at_root_rejected(self) -> None:
        with pytest.raises(ValueError):
            SelfForkSettings(bogus="value")  # type: ignore[call-arg]

    def test_unknown_field_in_subconfig_rejected(self) -> None:
        with pytest.raises(ValueError):
            RuntimeConfig(unknown_field="x")  # type: ignore[call-arg]

    def test_invalid_port_rejected(self) -> None:
        with pytest.raises(ValueError):
            RuntimeConfig(port=999_999)

    def test_invalid_backend_literal_rejected(self) -> None:
        with pytest.raises(ValueError):
            RuntimeConfig(backend="something-else")  # type: ignore[arg-type]

    def test_invalid_verifier_mode_rejected(self) -> None:
        with pytest.raises(ValueError):
            LifecycleConfig(verifier_mode="paranoid")  # type: ignore[arg-type]


class TestLoadSettings:
    def test_no_file_no_env_returns_defaults(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _clear_selffork_env(monkeypatch)
        s = load_settings()
        assert s.runtime.port == 8080

    def test_yaml_overrides_defaults(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cfg = tmp_path / "selffork.yaml"
        cfg.write_text("runtime:\n  port: 9999\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        _clear_selffork_env(monkeypatch)
        s = load_settings()
        assert s.runtime.port == 9999

    def test_env_overrides_yaml(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cfg = tmp_path / "selffork.yaml"
        cfg.write_text("runtime:\n  port: 9999\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        _clear_selffork_env(monkeypatch)
        monkeypatch.setenv("SELFFORK_RUNTIME__PORT", "7777")
        s = load_settings()
        assert s.runtime.port == 7777

    def test_explicit_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cfg = tmp_path / "custom.yaml"
        cfg.write_text("runtime:\n  port: 5555\n", encoding="utf-8")
        _clear_selffork_env(monkeypatch)
        s = load_settings(cfg)
        assert s.runtime.port == 5555

    def test_missing_explicit_path_raises(self) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_settings("/nonexistent/path-that-does-not-exist.yaml")

    def test_invalid_yaml_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cfg = tmp_path / "bad.yaml"
        cfg.write_text("[: this is unclosed\n  - and broken", encoding="utf-8")
        _clear_selffork_env(monkeypatch)
        with pytest.raises(ConfigError):
            load_settings(cfg)

    def test_unknown_field_in_yaml_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cfg = tmp_path / "selffork.yaml"
        cfg.write_text("runtime:\n  not_a_field: oops\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        _clear_selffork_env(monkeypatch)
        with pytest.raises(ConfigError):
            load_settings()

    def test_str_path_accepted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cfg = tmp_path / "selffork.yaml"
        cfg.write_text("runtime:\n  port: 4444\n", encoding="utf-8")
        _clear_selffork_env(monkeypatch)
        s = load_settings(str(cfg))
        assert s.runtime.port == 4444
