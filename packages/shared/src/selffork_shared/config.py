"""SelfFork configuration schema.

Pydantic v2 typed settings with three-layer precedence (high → low):

    1. ``SELFFORK_*`` environment variables (``__`` for nesting)
    2. ``selffork.yaml`` (or ``--config <path>``)
    3. Built-in defaults

Init kwargs sit above env (used by tests to override completely) and CLI
flags (passed by the orchestrator) sit on top of init. ``extra="forbid"``
means unknown fields fail validation at boot — no silent typo absorption.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §7.
"""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from selffork_shared.errors import ConfigError

__all__ = [
    "DEFAULT_CONFIG_NAMES",
    "AuditConfig",
    "CLIAgentConfig",
    "LifecycleConfig",
    "LoggingConfig",
    "PlanConfig",
    "RuntimeConfig",
    "SandboxConfig",
    "SelfForkSettings",
    "load_settings",
]

# Names of the config files to look for in the *current* working directory at
# load time. We resolve to absolute paths inside ``load_settings`` so chdir
# during a test or an embedded program is honoured.
DEFAULT_CONFIG_NAMES: tuple[str, ...] = ("selffork.yaml", "selffork.yml")

# Set per ``load_settings`` invocation so ``settings_customise_sources`` can
# pick up the YAML path without a global mutable. ``ContextVar`` keeps it
# thread- and async-safe in case multiple loads ever overlap.
_yaml_path_var: ContextVar[Path | None] = ContextVar("_yaml_path", default=None)


class _StrictModel(BaseModel):
    """Base for sub-config models. Forbids unknown fields recursively."""

    model_config = ConfigDict(extra="forbid")


class RuntimeConfig(_StrictModel):
    """LLM runtime backend configuration (for SelfFork Jr — the user simulator)."""

    backend: Literal["mlx-server", "ollama", "llama-cpp", "vllm"] = "mlx-server"
    # Default: smallest known PLE-safe MLX 4-bit Gemma 4 E2B-it variant.
    # See ``selffork.yaml`` comment block for fallback if this fails to load.
    model_id: str = "FakeRockert543/gemma-4-e2b-it-MLX-4bit"
    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=0, le=65535)  # mlx-lm default
    startup_timeout_seconds: int = Field(default=180, ge=1)
    health_check_interval_seconds: float = Field(default=2.0, gt=0)


class SandboxConfig(_StrictModel):
    """Isolation environment configuration."""

    mode: Literal["subprocess", "docker"] = "subprocess"
    workspace_root: str = "~/.selffork/workspaces"
    docker_image: str = "selffork/opencode-runtime:latest"
    docker_run_extra_args: list[str] = Field(default_factory=list)
    cpu_limit: float | None = None
    memory_limit_mb: int | None = None
    timeout_seconds: int = Field(default=3600, ge=1)


class CLIAgentConfig(_StrictModel):
    """CLI coding agent adapter configuration."""

    agent: Literal["opencode", "claude-code", "codex", "gemini-cli"] = "opencode"
    binary_path: str | None = None
    extra_args: list[str] = Field(default_factory=list)


class PlanConfig(_StrictModel):
    """Plan-as-state document store configuration."""

    backend: Literal["filesystem", "git"] = "filesystem"
    plan_filename: str = ".selffork/plan.json"


class LifecycleConfig(_StrictModel):
    """Session lifecycle configuration."""

    skip_verify: bool = False
    verifier_mode: Literal["noop", "lenient", "moderate", "strict"] = "lenient"
    # Optional cap on round-loop iterations (SelfFork-Jr ↔ CLI-agent
    # exchanges). ``None`` (the default) means unlimited — Jr keeps going
    # until it emits ``[SELFFORK:DONE]``. Set to a positive int only for
    # tests / safety drills; the wall-clock guard
    # (``sandbox.timeout_seconds``, default 1h) acts as the hard upper
    # bound either way.
    max_rounds: int | None = Field(default=None, ge=1)


class LoggingConfig(_StrictModel):
    """Structured logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json_output: bool = True
    log_dir: str = "~/.selffork/logs"


class AuditConfig(_StrictModel):
    """Audit log configuration."""

    enabled: bool = True
    audit_dir: str = "~/.selffork/audit"
    redact_secrets: bool = True


class SelfForkSettings(BaseSettings):
    """Top-level SelfFork settings.

    Loaded by :func:`load_settings`. Direct instantiation is supported but
    bypasses YAML resolution (useful in tests).
    """

    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    cli_agent: CLIAgentConfig = Field(default_factory=CLIAgentConfig)
    plan: PlanConfig = Field(default_factory=PlanConfig)
    lifecycle: LifecycleConfig = Field(default_factory=LifecycleConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)

    model_config = SettingsConfigDict(
        env_prefix="SELFFORK_",
        env_nested_delimiter="__",
        extra="forbid",
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Wire YAML between env and defaults so env wins, YAML beats defaults."""
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        path = _yaml_path_var.get()
        if path is not None and path.is_file():
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=path))
        sources.append(file_secret_settings)
        return tuple(sources)


def load_settings(config_path: Path | str | None = None) -> SelfForkSettings:
    """Load and validate :class:`SelfForkSettings` from YAML + env.

    Resolution:
        * If ``config_path`` is given, that file is used (raises if missing).
        * Else, :data:`DEFAULT_CONFIG_PATHS` are tried in order; first hit wins.
        * Else, defaults + env only.

    Precedence (high → low): ``SELFFORK_*`` env vars > YAML file > defaults.

    Raises:
        ConfigError: file missing/unreadable, YAML invalid, or schema validation
            failed (unknown field, type mismatch, out-of-range value).
    """
    path: Path | None = None
    if config_path is not None:
        path = Path(config_path).expanduser()
        if not path.is_file():
            raise ConfigError(f"config file not found: {path}")
    else:
        for name in DEFAULT_CONFIG_NAMES:
            candidate = Path.cwd() / name
            if candidate.is_file():
                path = candidate
                break

    token = _yaml_path_var.set(path)
    try:
        return SelfForkSettings()
    except ValidationError as exc:
        raise ConfigError(f"invalid config: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    finally:
        _yaml_path_var.reset(token)
