"""Jr-supervised child spawning — parser + runner.

When a parent SelfFork Jr reply carries one or more
``[SELFFORK:SPAWN: <spec>]`` markers, the orchestrator launches each
spec as an independent child session in its own tmux pane (against the
shared MLX runtime), waits for all to finish, and feeds the aggregated
outputs back to the parent as the next user-role message.

See: ``packages/orchestrator/src/selffork_orchestrator/spawn/sentinel.py``.
"""

from __future__ import annotations

from selffork_orchestrator.spawn.runner import (
    SpawnRunnerConfig,
    TmuxSpawnRunner,
)
from selffork_orchestrator.spawn.sentinel import (
    SpawnRequest,
    extract_spawn_requests,
)

__all__ = [
    "SpawnRequest",
    "SpawnRunnerConfig",
    "TmuxSpawnRunner",
    "extract_spawn_requests",
]
