"""Live Run Theater — round-loop event store + domain models + producer.

The theater (ADR-007 §4 S2) is the Workspace "Live Run" surface: a
per-workspace ordered stream of round-loop events (CLI output, Self Jr
thoughts) plus the live ``active_loops`` state. The round-loop's
``StoreTheaterProducer`` writes here; the theater WebSocket tails the
event stream and the snapshot / ``GET /api/loop/active`` endpoints read
it — the same store-tail decoupling the Talk and chat surfaces use, which
is also how the dashboard process reads state a separate ``selffork run``
process produced. Screenshots (the third theater pane) have no producer
in S2; that pane renders an honest empty state.
"""

from selffork_orchestrator.theater.models import (
    ActiveLoopRecord,
    CliOutputPayload,
    TheaterEvent,
    ThoughtPayload,
)
from selffork_orchestrator.theater.producer import (
    NullTheaterProducer,
    StoreTheaterProducer,
    TheaterProducer,
)
from selffork_orchestrator.theater.store import TheaterStore

__all__ = [
    "ActiveLoopRecord",
    "CliOutputPayload",
    "NullTheaterProducer",
    "StoreTheaterProducer",
    "TheaterEvent",
    "TheaterProducer",
    "TheaterStore",
    "ThoughtPayload",
]
