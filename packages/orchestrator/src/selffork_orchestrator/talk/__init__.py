"""Talk surface — operator ↔ Self Jr conversation store + domain models.

Talk (ADR-007 §4 S1) is the operator's direct conversation with Self Jr,
the Speaker model — distinct from the CLI-session chat in
:mod:`selffork_orchestrator.chat`, which mirrors a ``selffork run``
round-loop. Talk conversations are flat threads (no branching) persisted
to their own SQLite file so the cockpit keeps history across orchestrator
restarts.
"""

from selffork_orchestrator.talk.models import Conversation, TalkMessage
from selffork_orchestrator.talk.store import TalkStore

__all__ = ["Conversation", "TalkMessage", "TalkStore"]
