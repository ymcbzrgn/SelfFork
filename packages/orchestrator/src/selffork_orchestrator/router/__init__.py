"""CLI router (ADR-006 §4.6 / ADR-007 §4 S6).

Self Jr's "which CLI **and model** for this task" decision: operator
override → quota filter (per-model for gemini) → RAG affinity argmax,
with the chosen CLI's effort resolved from the Self-Jr-mutable control
config. No rotation, no cost. The affinity store lives in Mind
(dual-pool); this package owns the orchestrator-side selection, the
operator override store, the per-CLI runtime config, and the DuckDB
lifecycle.
"""

from __future__ import annotations

from selffork_orchestrator.router.affinity import (
    CliAffinityProvider,
    CLIRouter,
    CliSelection,
    ModelQuotaReader,
    QuotaExhaustedAcrossFleetError,
    SelectionMethod,
)
from selffork_orchestrator.router.affinity_snapshot import (
    affinity_snapshot_path,
    read_affinity_snapshot,
    write_affinity_snapshot,
)
from selffork_orchestrator.router.cli_config import (
    CliRuntimeConfig,
    CliRuntimeStore,
    default_cli_runtime_config_path,
    default_cli_runtime_store,
)
from selffork_orchestrator.router.outcomes import (
    OutcomeIngester,
    SessionOutcome,
    append_session_outcome,
    default_outcome_log_path,
)
from selffork_orchestrator.router.override import (
    CliOverride,
    CliOverrideStore,
    OverrideTarget,
    StickyOverrides,
    default_cli_override_path,
    default_cli_override_store,
)

__all__ = [
    "CLIRouter",
    "CliAffinityProvider",
    "CliOverride",
    "CliOverrideStore",
    "CliRuntimeConfig",
    "CliRuntimeStore",
    "CliSelection",
    "ModelQuotaReader",
    "OutcomeIngester",
    "OverrideTarget",
    "QuotaExhaustedAcrossFleetError",
    "SelectionMethod",
    "SessionOutcome",
    "StickyOverrides",
    "affinity_snapshot_path",
    "append_session_outcome",
    "default_cli_override_path",
    "default_cli_override_store",
    "default_cli_runtime_config_path",
    "default_cli_runtime_store",
    "default_outcome_log_path",
    "read_affinity_snapshot",
    "write_affinity_snapshot",
]
