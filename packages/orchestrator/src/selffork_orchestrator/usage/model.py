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
ProviderName = Literal["claude-code", "gemini-cli", "opencode", "codex"]


class ProviderUsage(BaseModel):
    """One row in ``GET /api/usage/providers``."""

    model_config = ConfigDict(extra="forbid")

    cli_agent: ProviderName
    window_label: str
    window_seconds: int
    calls_in_window: int
    next_reset_at: datetime | None
    last_rate_limited_at: datetime | None
