"""Pydantic schemas for the provider-usage strip.

Per ``project_provider_usage_source.md`` we ONLY surface what audit
logs prove. Each row in the dashboard strip corresponds to one
:class:`ProviderUsage` record; if a CLI never showed up in any audit
log, it does not get a row (we don't fabricate "0 calls" entries).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = ["ProviderName", "ProviderUsage"]

# Names match the CLIAgentConfig.agent literal values + the binary-
# inferred names used by audit_reader._infer_cli_from_binary.
ProviderName = Literal[
    "claude-code",
    "gemini-cli",
    "opencode",
    "codex",
    "minimax-cli",
]


class ProviderUsage(BaseModel):
    """One row in ``GET /api/usage/providers``.

    The audit-derived columns (``calls_in_window``,
    ``last_rate_limited_at``, ``next_reset_at``) come from
    :class:`UsageAggregator` walking the JSONL audit logs — the
    ``[[provider-usage-source]]`` ground truth, never displaced.

    The ``proactive_source`` annotation (S-Quota Wave 2) names which
    secondary layer also carries a snapshot for this CLI, so the
    Connections card can render a "Source: snapper | codexbar |
    snapper+codexbar" chip without conflating audit-truth with
    proactive data.
    """

    model_config = ConfigDict(extra="forbid")

    cli_agent: ProviderName
    window_label: str
    window_seconds: int
    calls_in_window: int
    next_reset_at: datetime | None
    last_rate_limited_at: datetime | None
    # S-Quota Wave 2 — lower-case dotted-prefix tag (``snapper``,
    # ``codexbar``, ``snapper+codexbar``) or ``None`` when no proactive
    # layer surfaces data for the row.
    proactive_source: str | None = None
