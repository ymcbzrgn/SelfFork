"""Self-Jr-mutable per-CLI runtime config — S6 (operator 2026-05-24).

> "effort, diğer configler falan filan hiçbiri hardcoded değil — Self Jr
> değiştirebilsin." SelfFork controls every CLI's model + effort, and
> Self Jr changes them natively (a tool mutates this store; the operator
> UI mutates it too). Nothing is baked into code.

Two knobs persisted here (model itself is **affinity-chosen** by the
router, or operator-overridden — see :mod:`selffork_orchestrator.router.override`):

* ``efforts`` — per-CLI reasoning-effort level. Seeded from the
  capability default (e.g. ``claude-code`` → ``max``, the operator's
  always-max habit) but fully overridable. The router passes the
  resolved effort to the CLIAgent, which applies it via the capability.
* ``enabled_models`` — per-CLI model subset the router may route to
  (empty ⇒ every capability model). Lets the operator / Self Jr narrow
  the candidate set without a code change.

Backed by the S4 :class:`YamlSettingsStore` (atomic write); validated
against :mod:`selffork_orchestrator.cli_agent.capabilities` so a typo'd
effort/model never lands on disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from selffork_orchestrator.cli_agent.capabilities import capability_for
from selffork_orchestrator.dashboard.settings.store import YamlSettingsStore

__all__ = [
    "CliRuntimeConfig",
    "CliRuntimeStore",
    "default_cli_runtime_config_path",
    "default_cli_runtime_store",
]


class CliRuntimeConfig(BaseModel):
    """Persisted per-CLI runtime knobs (Self-Jr-mutable)."""

    model_config = ConfigDict(extra="forbid")

    efforts: dict[str, str] = Field(default_factory=dict)
    enabled_models: dict[str, list[str]] = Field(default_factory=dict)


def default_cli_runtime_config_path() -> Path:
    """``~/.selffork/settings/cli_runtime.yaml``."""
    return Path("~/.selffork/settings/cli_runtime.yaml").expanduser()


@dataclass
class CliRuntimeStore:
    """Resolve + mutate per-CLI runtime config, validated by capability."""

    store: YamlSettingsStore[CliRuntimeConfig]

    def read(self) -> CliRuntimeConfig:
        return self.store.read_or_default()

    def effort_for(self, cli: str) -> str | None:
        """Resolved effort for ``cli`` — persisted value, else the
        capability seed default, else ``None``."""
        cfg = self.read()
        if cli in cfg.efforts:
            return cfg.efforts[cli]
        cap = capability_for(cli)
        return cap.effort.default if cap is not None else None

    def enabled_models_for(self, cli: str) -> tuple[str, ...] | None:
        """Operator/Self-Jr-narrowed model subset, or ``None`` (= all)."""
        models = self.read().enabled_models.get(cli)
        return tuple(models) if models else None

    def models_override(self) -> dict[str, tuple[str, ...]]:
        """All non-empty enabled-model subsets (for ``candidate_pairs``)."""
        return {cli: tuple(models) for cli, models in self.read().enabled_models.items() if models}

    def set_effort(self, *, cli: str, effort: str | None) -> None:
        """Set (or clear, with ``None``) the effort for ``cli``.

        Raises ``ValueError`` for an unknown CLI or an effort level the
        CLI does not support.
        """
        cap = capability_for(cli)
        if cap is None:
            raise ValueError(f"unknown cli: {cli!r}")
        if effort is not None and effort not in cap.effort.levels:
            raise ValueError(
                f"cli {cli!r} does not support effort {effort!r}; valid: {list(cap.effort.levels)}"
            )
        cfg = self.read()
        efforts = dict(cfg.efforts)
        if effort is None:
            efforts.pop(cli, None)
        else:
            efforts[cli] = effort
        self.store.write(cfg.model_copy(update={"efforts": efforts}))

    def set_enabled_models(self, *, cli: str, models: list[str]) -> None:
        """Narrow ``cli`` to ``models`` (empty list ⇒ clear ⇒ all).

        Raises ``ValueError`` for an unknown CLI or model.
        """
        cap = capability_for(cli)
        if cap is None:
            raise ValueError(f"unknown cli: {cli!r}")
        invalid = [m for m in models if not cap.has_model(m)]
        if invalid:
            raise ValueError(f"unknown models for {cli!r}: {invalid}")
        cfg = self.read()
        enabled = dict(cfg.enabled_models)
        if models:
            enabled[cli] = list(models)
        else:
            enabled.pop(cli, None)
        self.store.write(cfg.model_copy(update={"enabled_models": enabled}))


def default_cli_runtime_store() -> CliRuntimeStore:
    """Build the default YAML-backed runtime store."""
    return CliRuntimeStore(
        store=YamlSettingsStore(
            path=default_cli_runtime_config_path(),
            schema=CliRuntimeConfig,
            default_factory=CliRuntimeConfig,
        )
    )
