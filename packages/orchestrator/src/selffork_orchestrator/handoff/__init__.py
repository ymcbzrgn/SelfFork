"""Cross-CLI session-state handoff bundles.

When the round-loop driver swaps from one CLI agent to another (quota
exhaustion → ``rotate_to(codex)``, manual operator override, etc.), it
serializes the active session state into a :class:`HandoffBundle` and
injects it into the new CLI's first user-role message + system message.

The bundle is normalized across CLIs so a single shape works regardless
of which CLI is incoming: ``active_task`` describes the work, ``transcript_recent``
carries the last N raw rounds, ``transcript_digest`` is an LLM-summary of
older rounds, ``memory_subset`` references Mind T1-T4 (not payload),
``tool_state`` carries cwd + env whitelist + open files.

Schema follows Letta ``.af`` AgentFileSchema patterns: Stripe-style
``handoff-<n>`` ids, ``schema_version`` for forward-compat, secrets
scrubbed on the way out (``env_whitelist`` is allow-list, never the full
process env).
"""
from __future__ import annotations

from selffork_orchestrator.handoff.bundle import (
    ActiveTask,
    CliId,
    HandoffBundle,
    MemorySubset,
    ToolState,
    TranscriptMessage,
)
from selffork_orchestrator.handoff.store import (
    HandoffBundleStore,
    default_handoff_root,
)

__all__ = [
    "ActiveTask",
    "CliId",
    "HandoffBundle",
    "HandoffBundleStore",
    "MemorySubset",
    "ToolState",
    "TranscriptMessage",
    "default_handoff_root",
]
