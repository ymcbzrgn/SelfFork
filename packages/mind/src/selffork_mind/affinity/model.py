"""CLI affinity scoring model — ADR-006 §4.6 + ADR-009 dual-pool (S6).

The CLI router (ADR-006 §4.6) picks a CLI by ``max(success_rate)`` over
the quota-eligible candidates. ADR-006 locks the *inputs* (operator
override → quota filter → RAG affinity argmax) but leaves the *math* of
``rag_performance_score`` open. S6 implements it as a **frequentist
success-rate, enriched without changing the deterministic argmax**:

* **Laplace prior** ``(S + alpha) / (S + F + alpha + beta)`` (alpha=beta=1) — an untried
  ``(task, cli)`` cell scores ``0.5`` instead of being undefined. This
  is the posterior mean of a ``Beta(1, 1)`` prior under Bernoulli
  observations: principled, yet fully deterministic (no sampling).
* **Per-observation recency decay** ``gamma`` — each new outcome discounts
  the running counts (exponential recency-weighted average), so a CLI's
  score tracks recent provider behaviour rather than ancient history.
* **Hierarchical backoff (partial pooling)** over the
  ``(workspace, task_type, cli, model)`` key — a sparse PROJECT leaf
  shrinks toward the GLOBAL ``(task, cli, model)`` estimate, then the
  GLOBAL ``(cli, model)`` aggregate, then the GLOBAL ``(cli)`` aggregate
  (model-agnostic — a known-good CLI lends its new models a prior), then
  the ``0.5`` prior. Shrinkage weight ``n / (n + k)`` grows with the
  leaf's observation count, so a leaf earns trust as evidence accrues.
  This mirrors the ADR-009 dual-pool split (PROJECT codebase affinity =
  leaf; GLOBAL operator reflex = shared prior).

None of this introduces a new *selection* algorithm: the resolver still
returns one deterministic score per CLI and the router still takes the
argmax. ``avg_turns`` (ADR-006 §7.3 schema) is recorded and used only as
a deterministic tie-break — fewer turns to ``[SELFFORK:DONE]`` wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

__all__ = [
    "AffinityConfig",
    "AffinityRecord",
    "AffinityScore",
    "MatchLevel",
    "laplace_rate",
    "shrink",
]


MatchLevel = Literal["project_leaf", "global_task", "global_cli_model", "global_cli", "prior"]
"""Deepest backoff level that carried real observations for a score.

``project_leaf`` = ``(workspace, task, cli, model)``; ``global_task`` =
``(task, cli, model)``; ``global_cli_model`` = ``(cli, model)`` over all
tasks; ``global_cli`` = ``(cli)`` over all models; ``prior`` = no data
(uniform ``0.5``).
"""


@dataclass(frozen=True, slots=True)
class AffinityConfig:
    """Tunable scoring parameters (ADR-006 §4.6 math, open by ADR).

    Attributes:
        alpha: Laplace success pseudo-count (Beta prior alpha). Must be > 0.
        beta: Laplace failure pseudo-count (Beta prior beta). Must be > 0.
            ``alpha == beta`` keeps the cold-start prior at ``0.5``.
        decay_gamma: Per-observation recency discount in ``(0, 1]``.
            ``1.0`` disables decay (counts never age); ``0.97`` keeps a
            ~33-observation effective memory. Applied at write time.
        shrinkage_k: Partial-pooling constant. A leaf with ``k``
            observations weights itself ``0.5`` against its parent. Must
            be >= 0; ``0`` disables pooling (leaf trusted immediately).
    """

    alpha: float = 1.0
    beta: float = 1.0
    decay_gamma: float = 0.97
    shrinkage_k: float = 4.0

    def __post_init__(self) -> None:
        if self.alpha <= 0.0 or self.beta <= 0.0:
            raise ValueError("alpha and beta must be > 0 (Beta prior)")
        if not 0.0 < self.decay_gamma <= 1.0:
            raise ValueError("decay_gamma must be in (0, 1]")
        if self.shrinkage_k < 0.0:
            raise ValueError("shrinkage_k must be >= 0")


@dataclass(frozen=True, slots=True)
class AffinityRecord:
    """One stored affinity cell — discounted counts for ``(task, cli)``.

    Counts are floats because per-observation decay produces fractional
    values. ``group_id`` (``p:<slug>`` / ``g:global``) encodes the pool
    the row belongs to (ADR-009 §1); within a pool the cell key is
    ``(task_type, cli)``. ``task_type`` is ``None`` when the producer had
    no task classification (the router still scores via backoff) and is
    also ``None`` on aggregate rows returned by ``aggregate_cli``.
    """

    group_id: str
    task_type: str | None
    cli: str
    model: str | None
    success: float
    failure: float
    total_turns: float
    observations: float
    last_used: datetime | None

    @property
    def avg_turns(self) -> float | None:
        """Mean turns-to-complete, or ``None`` when no observations."""
        if self.observations <= 0.0:
            return None
        return self.total_turns / self.observations


@dataclass(frozen=True, slots=True)
class AffinityScore:
    """The resolved score for one CLI candidate (router input).

    Attributes:
        cli: The candidate ``cli_id``.
        score: Smoothed, backed-off success-rate in ``[0, 1]``. The
            router takes ``argmax`` over this.
        match_level: Deepest backoff level that had observations — for
            audit/observability ("why this CLI").
        observations: Discounted observation count at the leaf level
            (``0`` when the leaf is empty — score came from a parent).
        avg_turns: Mean turns at ``match_level`` (deterministic tie-break
            input; ``None`` for ``prior``).
    """

    cli: str
    model: str
    score: float
    match_level: MatchLevel
    observations: float
    avg_turns: float | None


def laplace_rate(success: float, failure: float, config: AffinityConfig) -> float:
    """Laplace-smoothed success rate — ``(S + alpha) / (S + F + alpha + beta)``.

    Cold-start (``S == F == 0``) yields ``alpha / (alpha + beta)`` (``0.5`` when
    ``alpha == beta``). Always defined; always in ``(0, 1)``.
    """
    numerator = success + config.alpha
    denominator = success + failure + config.alpha + config.beta
    return numerator / denominator


def shrink(
    leaf_rate: float,
    leaf_observations: float,
    parent_rate: float,
    config: AffinityConfig,
) -> float:
    """Partial-pool a leaf estimate toward its parent.

    Weight ``w = n / (n + k)`` favours the leaf as observations ``n``
    accrue and falls back to ``parent_rate`` when the leaf is sparse.
    With ``k == 0`` the leaf is trusted immediately (``w == 1`` whenever
    ``n > 0``; an empty leaf still defers fully to the parent).
    """
    denom = leaf_observations + config.shrinkage_k
    if denom <= 0.0:
        # k == 0 and no observations — nothing to lean on but the parent.
        return parent_rate
    weight = leaf_observations / denom
    return weight * leaf_rate + (1.0 - weight) * parent_rate
