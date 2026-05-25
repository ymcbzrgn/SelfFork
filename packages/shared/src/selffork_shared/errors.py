"""Typed exception hierarchy for SelfFork.

Every error inherits from :class:`SelfForkError`. Domain umbrellas cluster
errors by source (Config / Runtime / Sandbox / Agent / Plan). Subclasses
narrow further. Every raise site picks the most specific subclass and
embeds enough context (paths, exit codes, command lines) to debug without
re-running.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §9.
"""

from __future__ import annotations

__all__ = [
    "AgentBinaryNotFoundError",
    "AgentError",
    "AgentExitError",
    "AgentParseError",
    "AgentSpawnError",
    "AgentTimeoutError",
    "ConfigError",
    "PlanError",
    "PlanLoadError",
    "PlanSaveError",
    "RuntimeError",
    "RuntimeMisconfiguredError",
    "RuntimeStartError",
    "RuntimeUnhealthyError",
    "SandboxError",
    "SandboxExecError",
    "SandboxSpawnError",
    "SandboxTeardownError",
    "SelfForkError",
    "SelfForkTimeoutError",
    "SpeakerStalledError",
    "TmuxError",
    "TmuxPaneError",
    "TmuxSessionError",
]


class SelfForkError(Exception):
    """Root for all SelfFork errors. Never raised directly — use a subclass."""


# ── Config ────────────────────────────────────────────────────────────────────


class ConfigError(SelfForkError):
    """Configuration is invalid, missing, or contradictory.

    Raised at boot when YAML / env / defaults can't validate cleanly.
    """


# ── LLM Runtime ───────────────────────────────────────────────────────────────


class RuntimeError(SelfForkError):
    """LLM runtime failure umbrella. Subclass for specifics.

    Note: this name shadows Python's built-in ``RuntimeError`` inside any
    module that imports it. That is intentional — SelfFork code should raise
    this typed error, not the bare Python one (per ADR-001 §9). Code that
    needs Python's built-in must import ``builtins.RuntimeError`` explicitly.
    """


class RuntimeStartError(RuntimeError):
    """Runtime subprocess failed to spawn or never became healthy in time."""


class RuntimeUnhealthyError(RuntimeError):
    """Runtime stopped responding mid-session."""


class RuntimeMisconfiguredError(RuntimeError):
    """Runtime appears to be the wrong server for the configured model.

    ADR-011 §3.5: surfaces e.g. the ``mlx_lm.server`` (text-only) on a
    Gemma 4 VLM hang class — the runtime loads weights but never emits
    tokens. A bounded warmup probe + canonical-spawn check raises this
    instead of letting the system hang indefinitely. Distinct from
    :class:`RuntimeUnhealthyError` (mid-session failure) and
    :class:`RuntimeStartError` (process never spawned / health failed).
    """


class SpeakerStalledError(RuntimeError):
    """Speaker stream went idle past ``stall_seconds`` without a token.

    ADR-011 §3.3: the idle-token watchdog. A streaming generation may
    legitimately take minutes-to-hours on CPU and is **not** a failure
    so long as tokens keep arriving. This error fires only when no token
    has arrived for the configured ``stall_seconds`` — i.e. the model is
    wedged, not merely slow. Callers surface "stalled" distinctly from
    "unhealthy" so a slow-but-live generation is never falsely cancelled.
    """


# ── Sandbox ───────────────────────────────────────────────────────────────────


class SandboxError(SelfForkError):
    """Sandbox failure umbrella."""


class SandboxSpawnError(SandboxError):
    """Sandbox could not be created (workspace dir, container start, etc.)."""


class SandboxExecError(SandboxError):
    """A process inside the sandbox failed to spawn or run."""


class SandboxTeardownError(SandboxError):
    """Sandbox cleanup failed (container stop, dir removal, etc.).

    Logged but generally non-fatal — the parent should continue with shutdown.
    """


# ── CLI Agent ─────────────────────────────────────────────────────────────────


class AgentError(SelfForkError):
    """CLI agent failure umbrella."""


class AgentBinaryNotFoundError(AgentError):
    """The CLI agent's binary could not be located on PATH or via config."""


class AgentSpawnError(AgentError):
    """Subprocess spawn for the CLI agent failed."""


class AgentParseError(AgentError):
    """A line from the agent's stdout could not be parsed as a known event."""


class AgentTimeoutError(AgentError):
    """The agent exceeded its session-wide timeout while running."""


class AgentExitError(AgentError):
    """Agent exited with a non-zero code that wasn't captured as a domain event."""


# ── Plan store ────────────────────────────────────────────────────────────────


class PlanError(SelfForkError):
    """Plan store failure umbrella."""


class PlanLoadError(PlanError):
    """Plan file is missing, malformed, or unreadable."""


class PlanSaveError(PlanError):
    """Plan could not be persisted (disk full, permission denied, etc.)."""


# ── Tmux driver ───────────────────────────────────────────────────────────────


class TmuxError(SelfForkError):
    """Tmux driver failure umbrella."""


class TmuxSessionError(TmuxError):
    """Tmux session create / kill / lookup failed."""


class TmuxPaneError(TmuxError):
    """Tmux pane create / send-keys / pipe-pane failed."""


# ── Generic ───────────────────────────────────────────────────────────────────


class SelfForkTimeoutError(SelfForkError):
    """A bounded SelfFork operation exceeded its timeout.

    Distinct from Python's built-in :class:`TimeoutError` so callers can
    catch SelfFork-specific timeouts without swallowing IO timeouts.
    """
