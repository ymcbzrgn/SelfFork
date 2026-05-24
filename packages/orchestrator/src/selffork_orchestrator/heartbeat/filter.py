"""Legal-action filter — deterministic rules layer (S-Auto Faz B).

ADR-008 §4.3 reactive layer: the deterministic rules layer is the **sole
source** of the legal action set; the deliberative model (Faz C) only
selects from what this filter emits. Operator behaviour is fully knob-
driven (ADR-008 §7 Lock #3 + Lock #12) — nothing about which action is
legal is hardcoded outside this module.

Rules implemented in Faz B (each tied to one ADR-008 §6 safety layer):

1. **Pause flag** — operator ``/pause`` writes
   ``~/.selffork/pause.flag``. Only ``WAIT`` / ``SELF_STOP`` legal.
2. **Active-hours gate** — outside the configured window only ``WAIT``
   is legal (the daemon must still be able to respond to ``/pause``
   by selecting ``WAIT`` cleanly).
3. **Concurrency cap** — when ``active_concurrent_sessions >=
   max_concurrent_sessions`` the ``TASK_START`` action drops out
   (the inner round-loop is already saturated).
4. **Quota gate** — when *every* tracked CLI has
   :meth:`QuotaSnapshot.is_exhausted` above the threshold, both
   ``TASK_START`` and ``CLI_SELECT`` drop out (no provider can
   actually take new work).
5. **Creative toggle** — when Yaratma mode is OFF (Faz F default
   pre-M7) ``IDEATE`` drops out.

Rules deferred:

* **"Denetimli" preset** (ADR-008 §5.5) wraps each non-``WAIT``
  decision in a Telegram approval step. Faz G wires the wrap; Faz B
  exposes :attr:`WorldState.supervised_mode` as a marker so the wrap
  has its hook point but does not alter the legal set itself.
* **Per-CLI quota** filtering for ``TASK_START`` is collective in
  Faz B (all-exhausted ⇒ removed). Per-CLI picker happens inside the
  S6 router stub the Faz D ``cli_select`` action calls.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from selffork_orchestrator.heartbeat.actions import LegalAction
from selffork_orchestrator.heartbeat.config import HeartbeatConfig
from selffork_orchestrator.telegram.inbound_router import PauseSignal
from selffork_shared.quota import QuotaSnapshot

__all__ = [
    "DEFAULT_CLI_IDS",
    "DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT",
    "LegalActionFilter",
    "WorldState",
    "WorldStateBuilder",
]


DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT: Final[float] = 90.0
"""Default ``QuotaSnapshot.is_exhausted`` threshold for the quota gate.

ADR-008 §11 #1 family — operator-tunable in Faz G Settings UI. 90% is
slightly more conservative than the QuotaSnapshot default of 95% so the
filter prevents the daemon from starting work that the inner round-loop
would immediately rate-limit on.
"""


DEFAULT_CLI_IDS: Final[tuple[str, ...]] = (
    "claude-code",
    "codex",
    "gemini-cli",
    "opencode",
)
"""SelfFork coding-CLI ``cli_id``s the quota gate + router inspect by default.

``minimax-cli`` is deliberately EXCLUDED (S6, 2026-05-24): ``mmx`` is
MiniMax's generation CLI, not a coding agent — MiniMax coding routes via
opencode -> MiniMax-M2.7 (see
``project_minimax_cli_dropped_2026_05_24.md``). The minimax-cli adapter +
quota snapper are retained for manual / tracking use only. Override
per-instance to support custom CLI deployments.
"""


# ── WorldState ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WorldState:
    """Deterministic snapshot of orchestrator state for one Heartbeat tick.

    Built by :class:`WorldStateBuilder` at the start of each tick and
    fed to :meth:`LegalActionFilter.legal_actions`. Every field is what
    the filter needs to compute the legal set — adding more fields
    means a corresponding rule in :class:`LegalActionFilter`.

    Attributes:
        pause_active: ``True`` when the operator has requested a pause.
        within_active_hours: ``True`` when the current time falls inside
            the operator's configured active window.
        active_concurrent_sessions: Number of inner round-loop sessions
            currently in flight (0 when none).
        max_concurrent_sessions: Configured cap (ADR-008 §11 #2).
        creative_mode_enabled: ``True`` when Yaratma mode is on
            (Faz F wires the actual toggle; Faz B reads the static
            config value).
        cli_quota: Per-``cli_id`` :class:`QuotaSnapshot` (or ``None`` if
            the layer is missing data). ``None`` is treated as "no
            signal" — neither healthy nor exhausted.
        quota_exhaustion_threshold_pct: Threshold passed to
            :meth:`QuotaSnapshot.is_exhausted` (default 90.0).
        supervised_mode: Marker for the ADR-008 §5.5 "Denetimli" preset.
            Faz G wraps each non-``WAIT`` selection in a Telegram
            approval; Faz B does not act on this flag yet.
        last_active_workspace: Slug of the workspace the operator last
            interacted with (TalkStore source). ``None`` when there is
            no recent operator activity.
    """

    pause_active: bool
    within_active_hours: bool
    active_concurrent_sessions: int
    max_concurrent_sessions: int
    creative_mode_enabled: bool
    cli_quota: Mapping[str, QuotaSnapshot | None] = field(default_factory=dict)
    quota_exhaustion_threshold_pct: float = (
        DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT
    )
    supervised_mode: bool = False
    last_active_workspace: str | None = None

    def cli_has_quota(self, cli_id: str) -> bool:
        """Return ``True`` when ``cli_id`` is not exhausted.

        Treats missing snapshots as "no signal ⇒ assume healthy" to
        avoid silencing the daemon over an absent proactive layer.
        Callers that need stricter behaviour read :attr:`cli_quota`
        directly.
        """
        snap = self.cli_quota.get(cli_id)
        if snap is None:
            return True
        return not snap.is_exhausted(self.quota_exhaustion_threshold_pct)

    def any_cli_has_quota(self) -> bool:
        """``True`` when at least one tracked CLI is not exhausted."""
        if not self.cli_quota:
            # No tracked CLIs ⇒ no quota signal ⇒ don't gate.
            return True
        return any(self.cli_has_quota(cli) for cli in self.cli_quota)


# ── WorldStateBuilder ────────────────────────────────────────────────


_QuotaReader = Callable[[str], Awaitable[QuotaSnapshot | None]]
"""Async function ``(cli_id) → QuotaSnapshot | None``.

The dashboard wires this to :meth:`CodexBarFallbackReader.read`. Tests
inject canned readers without touching httpx.
"""


_ConcurrencyProbe = Callable[[], int]
"""Sync function returning the current inner-loop session count.

Faz D wires a real counter; Faz B stubs to ``lambda: 0``.
"""


_TalkLastWorkspaceProbe = Callable[[], Awaitable[str | None]]
# S7 — workspace-scope eligibility gate (ADR-007 §4 S7). Given the
# slug the talk probe returned, the gate decides whether Heartbeat
# may target that workspace this tick (``True`` = eligible). The
# default wiring in :func:`build_default_heartbeat` consults
# :class:`ProjectStore` so ``archived_at`` and ``autopilot_paused``
# drop the workspace out of the WorldState; tests can pass an
# arbitrary callable.
_WorkspaceEligibleProbe = Callable[[str], Awaitable[bool]]
"""Async function returning the last active workspace slug from TalkStore."""


class WorldStateBuilder:
    """Build a :class:`WorldState` per Heartbeat tick.

    Dependencies are optional + composed: anything ``None`` degrades the
    corresponding field to a safe default (no probe ⇒ assume healthy).
    This keeps Faz B usable before Faz D/F wire real producers.
    """

    def __init__(
        self,
        *,
        config: HeartbeatConfig,
        pause_signal: PauseSignal,
        quota_reader: _QuotaReader | None = None,
        concurrency_probe: _ConcurrencyProbe | None = None,
        talk_last_workspace_probe: _TalkLastWorkspaceProbe | None = None,
        workspace_eligible_probe: _WorkspaceEligibleProbe | None = None,
        creative_mode_provider: Callable[[], bool] | None = None,
        supervised_mode_provider: Callable[[], bool] | None = None,
        within_active_hours_probe: Callable[[], bool] | None = None,
        cli_ids: Sequence[str] = DEFAULT_CLI_IDS,
        quota_threshold_pct: float = DEFAULT_QUOTA_EXHAUSTION_THRESHOLD_PCT,
    ) -> None:
        self._config = config
        self._pause = pause_signal
        self._quota_reader = quota_reader
        self._concurrency = concurrency_probe
        self._talk_last_workspace = talk_last_workspace_probe
        self._workspace_eligible = workspace_eligible_probe
        self._creative_mode = creative_mode_provider
        self._supervised_mode = supervised_mode_provider
        self._within_active_hours = within_active_hours_probe
        self._cli_ids = tuple(cli_ids)
        self._quota_threshold_pct = quota_threshold_pct

    async def build(self) -> WorldState:
        """Snapshot the orchestrator state."""
        pause_active = self._pause.is_set()
        within_active_hours = (
            self._within_active_hours()
            if self._within_active_hours is not None
            else True
        )
        active_concurrent = (
            self._concurrency() if self._concurrency is not None else 0
        )
        creative_enabled = (
            self._creative_mode() if self._creative_mode is not None else False
        )
        supervised = (
            self._supervised_mode()
            if self._supervised_mode is not None
            else False
        )
        cli_quota: dict[str, QuotaSnapshot | None] = {}
        if self._quota_reader is not None:
            for cli_id in self._cli_ids:
                try:
                    cli_quota[cli_id] = await self._quota_reader(cli_id)
                except Exception:
                    cli_quota[cli_id] = None
        else:
            cli_quota = {cli_id: None for cli_id in self._cli_ids}

        last_workspace: str | None = None
        if self._talk_last_workspace is not None:
            try:
                last_workspace = await self._talk_last_workspace()
            except Exception:
                last_workspace = None
        # S7 — workspace eligibility gate. ``autopilot_paused`` or
        # ``archived_at`` drops the workspace from the WorldState so
        # downstream actions (``TASK_START``, ``CLI_SELECT``) never
        # target it. Fail-OPEN on gate exceptions (matches the
        # active-hours probe convention) so a transient ProjectStore
        # read error doesn't accidentally silence Self Jr.
        if last_workspace is not None and self._workspace_eligible is not None:
            try:
                eligible = await self._workspace_eligible(last_workspace)
            except Exception:
                eligible = True
            if not eligible:
                last_workspace = None

        return WorldState(
            pause_active=pause_active,
            within_active_hours=within_active_hours,
            active_concurrent_sessions=active_concurrent,
            max_concurrent_sessions=self._config.max_concurrency,
            creative_mode_enabled=creative_enabled,
            cli_quota=cli_quota,
            quota_exhaustion_threshold_pct=self._quota_threshold_pct,
            supervised_mode=supervised,
            last_active_workspace=last_workspace,
        )


# ── LegalActionFilter ────────────────────────────────────────────────


_ALL_ACTIONS: Final[frozenset[LegalAction]] = frozenset(LegalAction)
_PAUSE_ALLOWED: Final[frozenset[LegalAction]] = frozenset(
    {LegalAction.WAIT, LegalAction.SELF_STOP}
)
_OUTSIDE_HOURS_ALLOWED: Final[frozenset[LegalAction]] = frozenset(
    {LegalAction.WAIT}
)


class LegalActionFilter:
    """Pure deterministic filter — :meth:`legal_actions` is a function of state.

    No async, no I/O. Tests instantiate without dependencies; the
    Heartbeat scheduler wires one instance per daemon. Adding a rule
    means a new ``if`` branch in :meth:`legal_actions` + a corresponding
    field on :class:`WorldState` — never branch on ``self`` state.
    """

    def legal_actions(self, state: WorldState) -> frozenset[LegalAction]:
        """Compute the legal set for ``state``.

        Returns an immutable :class:`frozenset` so callers cannot mutate
        an authoritative legal set in place (defence-in-depth: model
        adapters must request a new filter call to widen their options).
        """
        # Rule 1 — pause short-circuits everything.
        if state.pause_active:
            return _PAUSE_ALLOWED

        # Rule 2 — outside active hours is a hard "do nothing" gate.
        if not state.within_active_hours:
            return _OUTSIDE_HOURS_ALLOWED

        legal = set(_ALL_ACTIONS)

        # Rule 3 — concurrency cap removes TASK_START only.
        if (
            state.active_concurrent_sessions
            >= state.max_concurrent_sessions
        ):
            legal.discard(LegalAction.TASK_START)

        # Rule 4 — every tracked CLI exhausted ⇒ no provider can run.
        if not state.any_cli_has_quota():
            legal.discard(LegalAction.TASK_START)
            legal.discard(LegalAction.CLI_SELECT)

        # Rule 5 — Yaratma mode toggle removes IDEATE when off.
        if not state.creative_mode_enabled:
            legal.discard(LegalAction.IDEATE)

        return frozenset(legal)
