"""Pydantic schemas for per-topic operator settings stores (S4).

These mirror the operator's view of Settings UI fields one-to-one so
the GET/PUT round trip is trivial. Each schema is the entire payload
written to its own ``~/.selffork/settings/<topic>.yaml`` file.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "CodexBarUserConfig",
    "ModelEndpointConfig",
    "ModelEndpointHealth",
]


class ModelEndpointConfig(BaseModel):
    """Self Jr Talk endpoint config (URL / protocol / model / auth).

    The endpoint Self Jr uses to reach its model. Operator tunes via
    the Settings UI; restart-required — the dashboard's deliberation
    layer + Heartbeat scheduler read these values at construction
    time, so a live change takes effect on next dashboard boot.
    """

    model_config = ConfigDict(extra="forbid")

    url: str = "http://127.0.0.1:8080"
    """Endpoint base URL (e.g. ``http://192.168.1.10:8080``)."""

    protocol: Literal["openai", "mlx", "ollama"] = "openai"
    """Wire protocol. OpenAI-compatible covers most providers; MLX
    raw and Ollama exist for self-host fallback."""

    model_name: str = "gemma-4-e2b-it"
    """Model identifier sent in request bodies (``model`` field for
    OpenAI-compatible, ``model`` for Ollama, model path for MLX)."""

    auth_kind: Literal["none", "api-key", "bearer"] = "none"
    """How ``auth_secret`` is sent. ``none`` omits the header
    entirely; ``api-key`` sends ``Authorization: Bearer <secret>``
    (OpenAI compat); ``bearer`` sends a raw ``Bearer <secret>``."""

    auth_secret: str = ""
    """Auth secret. Stored plain in the operator-local YAML —
    SelfFork is single-operator on a single machine, so secrets in
    ``~/.selffork/`` are no more sensitive than the operator's shell
    history. Empty when ``auth_kind == 'none'``."""

    training_endpoint: str = ""
    """Separate training endpoint URL (M7 reflex). Empty falls back
    to ``url`` (operator runs training on the same machine that
    serves inference)."""


class ModelEndpointHealth(BaseModel):
    """Response shape for the ``/test`` health-ping endpoint."""

    ok: bool
    """Whether the ``GET <url>/v1/models`` (or protocol equivalent)
    responded with a 2xx status inside the timeout window."""

    status_code: int | None = None
    """HTTP status from the probe, ``None`` on transport error."""

    latency_ms: int | None = None
    """Round-trip in milliseconds for the probe request."""

    detail: str = ""
    """Free-form diagnostic text (server name / error class /
    response body excerpt). Surfaced verbatim in the UI under the
    health pill."""


class CodexBarUserConfig(BaseModel):
    """CodexBar sidecar user-tunable knobs (S4 Settings UI).

    Distinct from
    :class:`selffork_orchestrator.snappers.codexbar_server.CodexBarServerConfig`
    which is the runtime config (port / refresh interval / timeouts)
    resolved from env and not surfaced to the operator.
    """

    model_config = ConfigDict(extra="forbid")

    version_pin: str = ""
    """Pin to a specific CodexBar release (e.g. ``v0.27.0``). Empty
    uses the vendored manifest default. The actual binary swap is a
    manual step (``infra/deploy/scripts/install-codexbar.sh`` or the
    next ``codexbar-watch`` CI PR) — this flag records the operator's
    intent so the UI shows it consistently."""

    auto_update: bool = True
    """Whether the operator opts in to weekly auto-update PRs from
    ``.github/workflows/codexbar-watch.yml``. Local toggle —
    the GitHub Actions cron runs from repository settings — but the
    Settings UI uses this to display the operator's preference."""

    binary_path_override: str = ""
    """Absolute path to a specific ``codexbar`` binary. Empty falls
    back to the layered defaults
    (``SELFFORK_CODEXBAR_BIN`` env > PATH search > vendored
    ``infra/deploy/codexbar/<platform>/codexbar``). When set, the
    next dashboard boot uses this path verbatim."""
