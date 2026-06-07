"""Operator CLI+model override store — ADR-006 §4.6 input #1 (S6).

The strongest router signal: an explicit operator override beats quota +
affinity. An override targets a CLI and **optionally a model** within it:

* ``cli`` only → the router still affinity-picks the best model inside
  that CLI ("use Gemini here; you choose the model").
* ``cli`` + ``model`` → both forced ("use codex gpt-5.3-codex").

Two flavours, per ADR-006 §4.6 + §4.7.2:

* **sticky** — persists across sessions (YAML); applies until cleared.
  ``/cli`` is sticky by default.
* **single-turn** — a one-shot consumed by the next
  :meth:`CliOverrideStore.get_active`; in-memory only.

Sticky overrides reuse the S4 :class:`YamlSettingsStore` atomic-write
plumbing so a crash mid-write never corrupts the operator's choice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from selffork_orchestrator.dashboard.settings.store import YamlSettingsStore

__all__ = [
    "CliOverride",
    "CliOverrideStore",
    "OverrideTarget",
    "StickyOverrides",
    "default_cli_override_path",
    "default_cli_override_store",
]


class OverrideTarget(BaseModel):
    """A persisted override target — a CLI and an optional model."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    cli: str
    model: str | None = None


class StickyOverrides(BaseModel):
    """Persisted sticky overrides — ``workspace_slug → OverrideTarget``."""

    model_config = ConfigDict(extra="forbid")

    overrides: dict[str, OverrideTarget] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CliOverride:
    """A resolved operator override for one workspace."""

    workspace: str
    cli: str
    model: str | None
    sticky: bool


def default_cli_override_path() -> Path:
    """``~/.selffork/settings/cli_override.yaml`` (mirrors telegram.yaml)."""
    return Path("~/.selffork/settings/cli_override.yaml").expanduser()


def default_cli_override_store() -> YamlSettingsStore[StickyOverrides]:
    """Build the default sticky-override YAML store."""
    return YamlSettingsStore(
        path=default_cli_override_path(),
        schema=StickyOverrides,
        default_factory=StickyOverrides,
    )


@dataclass
class CliOverrideStore:
    """Per-workspace operator override resolver.

    Sticky overrides live in ``sticky_store`` (persisted); single-turn
    overrides live in ``_single_turn`` (in-memory, consume-once). When
    both exist for a workspace, the single-turn nudge wins (the more
    recent, more specific intent) and is consumed first.
    """

    sticky_store: YamlSettingsStore[StickyOverrides]
    _single_turn: dict[str, OverrideTarget] = field(default_factory=dict)

    def set(
        self,
        *,
        workspace: str,
        cli: str,
        model: str | None = None,
        sticky: bool,
    ) -> CliOverride:
        """Record an override. ``sticky`` persists; otherwise one-shot."""
        target = OverrideTarget(cli=cli, model=model)
        if sticky:
            self._single_turn.pop(workspace, None)
            data = self.sticky_store.read_or_default()
            overrides = dict(data.overrides)
            overrides[workspace] = target
            self.sticky_store.write(data.model_copy(update={"overrides": overrides}))
        else:
            self._single_turn[workspace] = target
        return CliOverride(workspace=workspace, cli=cli, model=model, sticky=sticky)

    def peek(self, workspace: str) -> CliOverride | None:
        """Return the active override **without** consuming a one-shot."""
        target = self._single_turn.get(workspace)
        if target is not None:
            return CliOverride(
                workspace=workspace,
                cli=target.cli,
                model=target.model,
                sticky=False,
            )
        return self._sticky_override(workspace)

    def get_active(self, workspace: str) -> CliOverride | None:
        """Return the active override, **consuming** a pending one-shot."""
        target = self._single_turn.pop(workspace, None)
        if target is not None:
            return CliOverride(
                workspace=workspace,
                cli=target.cli,
                model=target.model,
                sticky=False,
            )
        return self._sticky_override(workspace)

    def clear(self, workspace: str) -> bool:
        """Drop both sticky + one-shot overrides for ``workspace``."""
        removed = self._single_turn.pop(workspace, None) is not None
        data = self.sticky_store.read_or_default()
        if workspace in data.overrides:
            overrides = dict(data.overrides)
            del overrides[workspace]
            self.sticky_store.write(data.model_copy(update={"overrides": overrides}))
            removed = True
        return removed

    def list_sticky(self) -> dict[str, OverrideTarget]:
        """All persisted sticky overrides (``workspace → target``)."""
        return dict(self.sticky_store.read_or_default().overrides)

    def _sticky_override(self, workspace: str) -> CliOverride | None:
        target = self.sticky_store.read_or_default().overrides.get(workspace)
        if target is None:
            return None
        return CliOverride(
            workspace=workspace,
            cli=target.cli,
            model=target.model,
            sticky=True,
        )
