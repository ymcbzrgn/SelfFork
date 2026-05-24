"""Per-CLI model + parameter capabilities — S6 (ADR-006 §4.6 / §4.7).

Describes WHAT each CLI agent exposes — its models, its reasoning/effort
knob, and how to *apply* a chosen model + effort at invoke time — so the
router can enumerate ``(cli, model)`` candidates and each
:class:`~selffork_orchestrator.cli_agent.base.CLIAgent` can inject the
selection into its command line.

Nothing here is a *selected* value: selections live in the
Self-Jr-mutable control config
(:mod:`selffork_orchestrator.router.cli_config`). This is the static
capability surface, **verified 2026-05-24 against the installed CLIs**:

* ``claude`` 2.1.150 — ``--model <alias>`` + ``--effort low|medium|high|xhigh|max``
* ``codex`` 0.130.0 — ``exec -m <model>`` + ``-c model_reasoning_effort=<minimal..xhigh>``
* ``gemini`` 0.39.1 — ``-m <model>`` (thinking via ``settings.json``, no flag)
* ``opencode`` 1.14.41 — ``run -m <provider/model>`` + ``--variant <effort>``
* ``mmx`` (MiniMax) — ``--model <model>`` (reasoning API-only, no flag)

Quota note (operator 2026-05-24): only ``gemini-cli`` has **per-model**
quota (pro / flash / flash-lite billed separately); the other CLIs share
one account-wide quota across their models. See :attr:`CliCapability.per_model_quota`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "CAPABILITIES",
    "CliCapability",
    "EffortApply",
    "EffortSpec",
    "candidate_pairs",
    "capability_for",
]


EffortApply = Literal["flag", "config_kv", "settings_file", "none"]
"""How a CLI applies its reasoning/effort knob.

* ``flag`` — a CLI flag taking the level (``--effort high`` / ``--variant high``).
* ``config_kv`` — a ``-c key=value`` override (``-c model_reasoning_effort=high``).
* ``settings_file`` — written to a settings file before invoke (gemini
  ``thinkingConfig``); the CLIAgent handles it, not :meth:`CliCapability.model_args`.
* ``none`` — the CLI exposes no per-invoke effort knob (minimax).
"""


@dataclass(frozen=True, slots=True)
class EffortSpec:
    """The reasoning/effort knob of one CLI."""

    apply: EffortApply
    levels: tuple[str, ...]
    default: str | None
    # flag name (``--effort``/``--variant``) or config key
    # (``model_reasoning_effort``); ``None`` for ``settings_file``/``none``.
    param: str | None = None

    def clamp(self, requested: str | None) -> str | None:
        """Return ``requested`` if a valid level, else the default.

        An unknown level (e.g. a model that does not support ``xhigh``)
        falls back to the configured default rather than erroring — the
        router never wedges on a stale level.
        """
        if requested is not None and requested in self.levels:
            return requested
        return self.default


@dataclass(frozen=True, slots=True)
class CliCapability:
    """Static model + effort surface for one ``cli_id``."""

    cli: str
    models: tuple[str, ...]
    default_model: str
    model_flag: str
    effort: EffortSpec
    per_model_quota: bool

    def has_model(self, model: str) -> bool:
        return model in self.models

    def model_args(
        self, *, model: str | None, effort: str | None
    ) -> list[str]:
        """CLI args injecting ``model`` + ``effort`` (flag/config_kv only).

        ``settings_file`` effort (gemini thinking) and ``none`` effort
        (minimax) contribute no args here — the model flag still applies,
        and the CLIAgent handles any settings-file write separately.
        """
        args: list[str] = []
        if model:
            args += [self.model_flag, model]
        # Only inject effort when one is explicitly requested — ``None``
        # means "leave the CLI's own default" (the seed/resolution lives
        # in the control config + router, not in this pure applier).
        if effort is not None and self.effort.param is not None:
            level = self.effort.clamp(effort)
            if level is not None:
                if self.effort.apply == "flag":
                    args += [self.effort.param, level]
                elif self.effort.apply == "config_kv":
                    args += ["-c", f"{self.effort.param}={level}"]
        return args


# ── Verified registry (2026-05-24) ───────────────────────────────────

CAPABILITIES: dict[str, CliCapability] = {
    "claude-code": CliCapability(
        cli="claude-code",
        models=(
            "opus",
            "sonnet",
            "haiku",
            "opusplan",
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
        ),
        default_model="opus",
        model_flag="--model",
        effort=EffortSpec(
            apply="flag",
            levels=("low", "medium", "high", "xhigh", "max"),
            default="max",  # operator seed (always-max habit); Self-Jr-overridable
            param="--effort",
        ),
        per_model_quota=False,
    ),
    "codex": CliCapability(
        cli="codex",
        models=(
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.3-codex",
            "gpt-5.2",
        ),
        default_model="gpt-5.5",
        model_flag="-m",
        effort=EffortSpec(
            apply="config_kv",
            levels=("minimal", "low", "medium", "high", "xhigh"),
            default="xhigh",
            param="model_reasoning_effort",
        ),
        per_model_quota=False,
    ),
    "gemini-cli": CliCapability(
        cli="gemini-cli",
        models=(
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ),
        default_model="gemini-2.5-pro",
        model_flag="-m",
        effort=EffortSpec(
            # Thinking is settings.json-only (no CLI flag); the gemini
            # CLIAgent writes a model-aware thinkingConfig — gated behind
            # experimental.dynamicModelConfiguration, written only when
            # effort != "dynamic" (opt-in; verified vs installed bundle
            # 2026-05-24). Symbolic level -> 2.5 thinkingBudget / 3 thinkingLevel.
            apply="settings_file",
            levels=("off", "low", "medium", "high", "dynamic"),
            default="dynamic",
            param=None,
        ),
        # gemini DOES bill per-model (pro/flash/flash-lite), but reading that
        # quota needs the Code Assist API (gemini-cli ToS violation + account-
        # ban risk, operator decision 2026-05-24) -> SelfFork tracks gemini
        # quota REACTIVELY only (GeminiRateLimitDetector 429/reset ->
        # ScheduledResume), and the proactive gate safe-degrades (the
        # per-model key never matches a ToS-clean source). See
        # project_gemini_quota_tos_2026_05_24.md.
        per_model_quota=True,
    ),
    "opencode": CliCapability(
        cli="opencode",
        # Non-Anthropic only (Claude routes through claude-code — see
        # [[cli-provider-routing]]). Operator-extendable via control config.
        models=(
            "openai/gpt-5.5",
            "openai/gpt-5.4",
            "z-ai/glm-4.6",
            "opencode/zen",
        ),
        default_model="openai/gpt-5.5",
        model_flag="-m",
        effort=EffortSpec(
            apply="flag",
            levels=("minimal", "low", "medium", "high", "xhigh"),
            default=None,  # provider default unless dialed
            param="--variant",
        ),
        per_model_quota=False,
    ),
    "minimax-cli": CliCapability(
        cli="minimax-cli",
        models=("MiniMax-M2.7", "MiniMax-M2.7-highspeed"),
        default_model="MiniMax-M2.7",
        model_flag="--model",
        effort=EffortSpec(
            apply="none", levels=(), default=None, param=None
        ),
        per_model_quota=False,
    ),
}


def capability_for(cli: str) -> CliCapability | None:
    """Capability for ``cli``, or ``None`` for an unknown CLI."""
    return CAPABILITIES.get(cli)


def candidate_pairs(
    clis: Iterable[str],
    *,
    models_override: dict[str, tuple[str, ...]] | None = None,
) -> list[tuple[str, str]]:
    """Enumerate ``(cli, model)`` candidates for the given CLIs.

    Each CLI contributes its capability models (or ``models_override[cli]``
    when the control config narrows the enabled set). Unknown CLIs are
    skipped. Order is stable (CLI order, then model order) so the router's
    final tie-break is deterministic.
    """
    pairs: list[tuple[str, str]] = []
    for cli in clis:
        cap = CAPABILITIES.get(cli)
        if cap is None:
            continue
        models = (
            models_override.get(cli, cap.models)
            if models_override is not None
            else cap.models
        )
        pairs.extend((cli, model) for model in models)
    return pairs
