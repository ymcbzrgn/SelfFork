"""Heartbeat scheduler configuration (S-Auto Faz A).

ADR-008 §4.2 + §11 #1/#2/#7: hybrid trigger (event-driven + reconciliation
timer), concurrency limit, active-hour gate. All knobs env-driven so the
Settings UI (Faz G) can persist + reload without a deploy — ADR-008 §7
Lock #12 ("every knob is configurable; nothing hardcoded").

Wave 1 default is opt-in (``SELFFORK_HEARTBEAT_ENABLED=true|1|yes``).
Once Faz B/C/D land and the smoke gate clears the default may flip to
opt-out (mirroring S-Quota Wave 2's CodexBar pattern) — that decision
belongs to Faz H, not here.
"""

from __future__ import annotations

import os
import zoneinfo
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from selffork_orchestrator.heartbeat.scheduler import HeartbeatScheduler

__all__ = [
    "DEFAULT_ACTIVE_HOURS",
    "DEFAULT_MAX_CONCURRENCY",
    "DEFAULT_RECONCILIATION_SECONDS",
    "DEFAULT_TICK_SECONDS",
    "DEFAULT_TIMEZONE",
    "HeartbeatConfig",
    "build_default_heartbeat",
    "build_default_heartbeat_config",
]


DEFAULT_TICK_SECONDS: Final[float] = 1.0
"""Inner tick cadence — how often the daemon wakes to check signals.

Independent of :data:`DEFAULT_RECONCILIATION_SECONDS`. Keeps shutdown
and pause-flag response time bounded (~1 s) without burning CPU.
"""

DEFAULT_RECONCILIATION_SECONDS: Final[float] = 600.0
"""Default safety-net world-state poll cadence — ADR-008 §11 #1 (10-15 min).

The reconciliation timer rereads the full world state (kanban + sessions
+ quota) even when no event fires, catching anything that escapes the
event-driven hot path.
"""

DEFAULT_MAX_CONCURRENCY: Final[int] = 1
"""Default cap on concurrent inner-loop sessions — ADR-008 §11 #2.

Operator watches one session "like a film" by default; Settings UI raises
this knob for power users.
"""

DEFAULT_ACTIVE_HOURS: Final[str] = "0:00-24:00"
"""Default 24/7 active window — ADR-008 §11 #7 ("uyumayan ikinci ben" ruhu).

Format: ``"HH:MM-HH:MM"`` 24-hour. ``24:00`` end means "all day".
Overnight windows wrap correctly (``"22:00-06:00"`` = 22:00 → next-day
06:00 — Hexis ``worker_service.py:185-188`` pattern).
"""

DEFAULT_TIMEZONE: Final[str] = "UTC"
"""Default IANA timezone for the active-hours comparison.

Operator overrides with e.g. ``SELFFORK_HEARTBEAT_TIMEZONE=Europe/Istanbul``.
Invalid value falls back to UTC silently — the daemon must never be
silenced by a typo.
"""


def _resolve_enabled() -> bool:
    raw = os.environ.get("SELFFORK_HEARTBEAT_ENABLED", "").strip().lower()
    return raw in {"true", "1", "yes"}


def _resolve_float(env_key: str, default: float, minimum: float = 0.05) -> float:
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _resolve_int(env_key: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _resolve_active_hours() -> str:
    raw = os.environ.get("SELFFORK_HEARTBEAT_ACTIVE_HOURS", "").strip()
    return raw or DEFAULT_ACTIVE_HOURS


def _resolve_timezone() -> str:
    raw = os.environ.get("SELFFORK_HEARTBEAT_TIMEZONE", "").strip()
    if not raw:
        return DEFAULT_TIMEZONE
    try:
        zoneinfo.ZoneInfo(raw)
    except zoneinfo.ZoneInfoNotFoundError:
        return DEFAULT_TIMEZONE
    return raw


@dataclass(frozen=True, slots=True)
class HeartbeatConfig:
    """Static config for one :class:`HeartbeatScheduler` instance.

    All knobs operator-tunable via env (and later Settings UI in Faz G);
    no autonomy behavior is hardcoded (ADR-008 §7 Lock #12).

    Attributes:
        enabled: ``True`` boots the daemon; ``False`` leaves it dormant.
        tick_seconds: Inner poll cadence (pause / shutdown responsiveness).
        reconciliation_seconds: Safety-net world-state poll cadence.
        max_concurrency: Cap on concurrent inner-loop sessions.
        active_hours: Window ``"HH:MM-HH:MM"`` of permitted ticks.
        timezone: IANA timezone for the active-hours comparison.
    """

    enabled: bool = False
    tick_seconds: float = DEFAULT_TICK_SECONDS
    reconciliation_seconds: float = DEFAULT_RECONCILIATION_SECONDS
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    active_hours: str = DEFAULT_ACTIVE_HOURS
    timezone: str = DEFAULT_TIMEZONE


def build_default_heartbeat_config() -> HeartbeatConfig:
    """Read env vars and return a :class:`HeartbeatConfig` for the dashboard.

    Env switches (all optional):

    * ``SELFFORK_HEARTBEAT_ENABLED=true|1|yes`` — opt-in for Wave 1.
    * ``SELFFORK_HEARTBEAT_TICK_SECONDS=<float>`` — inner poll cadence.
    * ``SELFFORK_HEARTBEAT_RECONCILIATION_SECONDS=<float>`` — safety net.
    * ``SELFFORK_HEARTBEAT_MAX_CONCURRENCY=<int>`` — concurrent sessions cap.
    * ``SELFFORK_HEARTBEAT_ACTIVE_HOURS="HH:MM-HH:MM"`` — permitted window.
    * ``SELFFORK_HEARTBEAT_TIMEZONE=<IANA name>`` — for active-hours.
    """
    return HeartbeatConfig(
        enabled=_resolve_enabled(),
        tick_seconds=_resolve_float(
            "SELFFORK_HEARTBEAT_TICK_SECONDS", DEFAULT_TICK_SECONDS
        ),
        reconciliation_seconds=_resolve_float(
            "SELFFORK_HEARTBEAT_RECONCILIATION_SECONDS",
            DEFAULT_RECONCILIATION_SECONDS,
        ),
        max_concurrency=_resolve_int(
            "SELFFORK_HEARTBEAT_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY
        ),
        active_hours=_resolve_active_hours(),
        timezone=_resolve_timezone(),
    )


def build_default_heartbeat(
    *,
    telegram_bridge: object | None = None,
    task_starter: object | None = None,
    kanban_card_creator: object | None = None,
) -> HeartbeatScheduler:
    """Construct the daemon from env (dashboard lifespan helper).

    Returns a :class:`HeartbeatScheduler` with config resolved from env
    and the default :class:`PauseSignal` wired. The deliberative layer
    (Faz C) auto-wires when both ``SELFFORK_TALK_MODEL_ENDPOINT`` and
    ``SELFFORK_TALK_MODEL`` are set — the same endpoint Talk uses, so a
    single Self Jr powers both surfaces (ADR-008 §12 unification note).
    When either env is missing the daemon ticks without selecting an
    action (Faz B behaviour preserved).

    Args:
        telegram_bridge: Optional
            :class:`selffork_orchestrator.telegram.bridge.TelegramBridge`
            instance for ``OPERATOR_ASK`` outbound messages
            (F-AG #3 wire — S4). Falls back to ``None`` (handler
            returns ``skipped``).
        task_starter: Optional coroutine matching
            :data:`selffork_orchestrator.heartbeat.executor.TaskStarter`
            that spawns ``selffork run`` for ``TASK_START`` decisions
            (F-AG #3 wire — S4).
        kanban_card_creator: Optional coroutine matching
            :data:`selffork_orchestrator.heartbeat.executor.KanbanCardCreator`
            that appends a card for ``KANBAN_SUGGEST`` decisions
            (F-AG #3 wire — S4).

    The parameters are typed ``object`` here to avoid pulling the
    heavy executor/telegram imports into :mod:`heartbeat.config`'s
    import surface; the executor itself validates the contract.

    Imports are local so :mod:`heartbeat.config` stays importable
    without instantiating the full PTB dependency chain.
    """
    from selffork_orchestrator.heartbeat.air import AIRDetector
    from selffork_orchestrator.heartbeat.audit import AuditWriter
    from selffork_orchestrator.heartbeat.autonomy import (
        AutonomyStore,
        CreativeDial,
        settings_to_heartbeat_config,
    )
    from selffork_orchestrator.heartbeat.checkpoint import CheckpointWriter
    from selffork_orchestrator.heartbeat.creative import IdeationManager
    from selffork_orchestrator.heartbeat.deliberation import DeliberationLayer
    from selffork_orchestrator.heartbeat.executor import ActionExecutor
    from selffork_orchestrator.heartbeat.filter import WorldStateBuilder
    from selffork_orchestrator.heartbeat.scheduler import (
        HeartbeatScheduler,
        compute_within_active_hours,
    )
    from selffork_orchestrator.talk.speaker import SpeakerClient
    from selffork_orchestrator.telegram.inbound_router import PauseSignal

    speaker_endpoint = os.environ.get(
        "SELFFORK_TALK_MODEL_ENDPOINT", ""
    ).strip()
    speaker_model = os.environ.get("SELFFORK_TALK_MODEL", "").strip()
    deliberation: DeliberationLayer | None = None
    if speaker_endpoint and speaker_model:
        deliberation = DeliberationLayer(
            speaker=SpeakerClient(
                base_url=speaker_endpoint, model=speaker_model
            ),
        )

    # F-AG #3 (S4): the dashboard process wires telegram_bridge /
    # task_starter / kanban_card_creator here; any of them may be
    # ``None`` (test fixtures, headless deployments) — the executor
    # falls back to a ``skipped`` outcome with a clear reason.
    # Ideation is always safe (Lab writes under ``~/.selffork/lab/``).
    executor = ActionExecutor(
        ideation_manager=IdeationManager(),
        telegram_bridge=telegram_bridge,  # type: ignore[arg-type]
        task_starter=task_starter,  # type: ignore[arg-type]
        kanban_card_creator=kanban_card_creator,  # type: ignore[arg-type]
    )

    # Settings UI wins when a YAML file exists; env is bootstrap only
    # (Faz G — Autonomy Settings panel). The dashboard's PUT endpoint
    # writes the file; this resolver picks it up on the next boot.
    autonomy_store = AutonomyStore.default()
    persisted = autonomy_store.read()
    pause = PauseSignal()
    creative_mode_provider: Callable[[], bool] | None
    supervised_mode_provider: Callable[[], bool] | None
    if persisted is not None:
        runtime_config = settings_to_heartbeat_config(persisted)
        _persisted = persisted  # capture for the closures below

        def _creative_provider() -> bool:
            return _persisted.creative_dial != CreativeDial.CLOSED

        def _supervised_provider() -> bool:
            return _persisted.supervised_mode

        creative_mode_provider = _creative_provider
        supervised_mode_provider = _supervised_provider
    else:
        runtime_config = build_default_heartbeat_config()
        creative_mode_provider = None
        supervised_mode_provider = None

    _runtime_config_for_probe = runtime_config

    def _active_hours_probe() -> bool:
        return compute_within_active_hours(
            _runtime_config_for_probe.active_hours,
            _runtime_config_for_probe.timezone,
        )

    world_state_builder = WorldStateBuilder(
        config=runtime_config,
        pause_signal=pause,
        within_active_hours_probe=_active_hours_probe,
        creative_mode_provider=creative_mode_provider,
        supervised_mode_provider=supervised_mode_provider,
    )

    return HeartbeatScheduler(
        config=runtime_config,
        pause_signal=pause,
        world_state_builder=world_state_builder,
        deliberation_layer=deliberation,
        action_executor=executor,
        audit_writer=AuditWriter.default(),
        checkpoint_writer=CheckpointWriter.default(),
        air_detector=AIRDetector(),
    )
