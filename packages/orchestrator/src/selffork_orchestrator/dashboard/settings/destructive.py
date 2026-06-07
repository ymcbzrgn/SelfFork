"""Destructive whitelist operator-override resolver (S4).

The destructive whitelist (ADR-006 §4.5) ships as a bundled YAML
inside the Body package
(:data:`selffork_body.sandbox.destructive_whitelist.DEFAULT_CONFIG_PATH`).
S4 adds an operator override at
``~/.selffork/settings/destructive-whitelist.yaml`` — when present it
fully replaces the bundle (no merge); when absent the bundle is in
effect.

Why no merge: the whitelist is an ordered policy. Allowing partial
override (e.g. patching just one category) creates surprise — an
operator's edits would silently mix with shipped defaults next time
the package updates them. Full-replace makes the override
self-contained and auditable.
"""

from __future__ import annotations

import os
from pathlib import Path

from selffork_body.sandbox.destructive_whitelist import (
    DEFAULT_CONFIG_PATH as BUNDLED_DESTRUCTIVE_PATH,
)
from selffork_body.sandbox.destructive_whitelist import DestructiveWhitelist

__all__ = [
    "BUNDLED_DESTRUCTIVE_PATH",
    "DEFAULT_DESTRUCTIVE_OVERRIDE_PATH",
    "destructive_whitelist_source",
    "load_effective_destructive_whitelist",
    "resolve_destructive_whitelist_path",
]


DEFAULT_DESTRUCTIVE_OVERRIDE_PATH: Path = Path(
    "~/.selffork/settings/destructive-whitelist.yaml"
).expanduser()
"""Operator override location. Mirror this in CLI + dashboard so the
runtime warden and the read endpoint stay in lockstep."""


def resolve_destructive_whitelist_path(
    override_path: Path | None = None,
) -> Path:
    """Return the effective whitelist file path.

    Args:
        override_path: Operator override location. Defaults to
            :data:`DEFAULT_DESTRUCTIVE_OVERRIDE_PATH`. Test fixtures
            pass a ``tmp_path``-rooted file so the resolver picks up
            the test sandbox state instead of the operator's real
            ``~/.selffork/`` tree.

    Precedence (highest → lowest):

    1. ``SELFFORK_DESTRUCTIVE_WHITELIST_PATH`` env var (operator pinned).
    2. ``override_path`` if the file exists.
    3. Bundled default (``DEFAULT_CONFIG_PATH``).
    """
    effective_override = (
        override_path if override_path is not None else DEFAULT_DESTRUCTIVE_OVERRIDE_PATH
    )
    env = os.environ.get("SELFFORK_DESTRUCTIVE_WHITELIST_PATH")
    if env:
        return Path(env).expanduser()
    if effective_override.is_file():
        return effective_override
    return BUNDLED_DESTRUCTIVE_PATH


def destructive_whitelist_source(
    override_path: Path | None = None,
) -> str:
    """Identify which file the warden is currently loading from.

    Used by the Settings GET endpoint so the UI can show ``Override``
    vs ``Default (bundled)`` next to the editor.
    """
    effective_override = (
        override_path if override_path is not None else DEFAULT_DESTRUCTIVE_OVERRIDE_PATH
    )
    env = os.environ.get("SELFFORK_DESTRUCTIVE_WHITELIST_PATH")
    if env:
        return "env"
    if effective_override.is_file():
        return "override"
    return "default"


def load_effective_destructive_whitelist(
    override_path: Path | None = None,
) -> DestructiveWhitelist:
    """Load the currently-effective :class:`DestructiveWhitelist`.

    Replaces the inline env-only resolver previously in
    ``selffork_orchestrator.cli._load_destructive_whitelist``; both
    surfaces (warden and dashboard) now share this single resolver.
    """
    return DestructiveWhitelist.load(resolve_destructive_whitelist_path(override_path))
