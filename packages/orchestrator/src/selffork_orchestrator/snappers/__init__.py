"""Per-CLI proactive quota snappers.

Each :class:`Snapper` reads a per-CLI signal source and projects it into a
normalized :class:`selffork_shared.quota.QuotaSnapshot`. The
:class:`SnapperRunner` owns lifecycle (start/stop/refresh cadence) and
atomically writes each snapshot to ``~/.selffork/cli-state/<cli_id>.json``.

Signal sources by CLI:

- ``claude-code`` — ``~/.claude/statusline.sh`` stdin JSON push (1s refresh)
- ``codex``       — ``~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`` TokenCountEvent tail
- ``gemini-cli``  — ``~/.gemini/telemetry.log`` OTel append + ``/stats model`` slash
- ``opencode``    — ``~/.local/share/opencode/opencode.db`` SQLite + ``GET /event`` SSE
- ``minimax-cli`` — (Order 7) ``mmx`` CLI quota endpoint

See ``project_provider_usage_source.md`` for the audit-log derivation discipline:
the proactive snapper layer complements (does not replace) audit-log derivation;
when a snapper signal is stale or unavailable, callers fall back to audit logs.
"""

from __future__ import annotations

from selffork_orchestrator.snappers.base import (
    Snapper,
    atomic_write_json,
    default_state_dir,
    snapshot_path,
)
from selffork_orchestrator.snappers.claude import ClaudeSnapper
from selffork_orchestrator.snappers.codex import CodexSnapper
from selffork_orchestrator.snappers.factory import (
    build_default_snappers,
    build_snapper,
    registered_snapper_ids,
)
from selffork_orchestrator.snappers.gemini import GeminiSnapper
from selffork_orchestrator.snappers.minimax import MinimaxSnapper
from selffork_orchestrator.snappers.opencode import OpenCodeSnapper
from selffork_orchestrator.snappers.runner import SnapperRunner, SnapperRunnerConfig
from selffork_orchestrator.snappers.zai import ZaiSnapper

__all__ = [
    "ClaudeSnapper",
    "CodexSnapper",
    "GeminiSnapper",
    "MinimaxSnapper",
    "OpenCodeSnapper",
    "Snapper",
    "SnapperRunner",
    "SnapperRunnerConfig",
    "ZaiSnapper",
    "atomic_write_json",
    "build_default_snappers",
    "build_snapper",
    "default_state_dir",
    "registered_snapper_ids",
    "snapshot_path",
]
