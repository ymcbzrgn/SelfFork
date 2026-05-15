"""Chat surface — branch store + ChatMessage / Branch domain.

Order 4 introduces conversation branching as a first-class concept
(memory: ``feedback_no_mvp_full_quality_first_time`` — UI surface
ships with the protocol, not a follow-up). Every Yamaç-edit forks a
new branch + a Mind T2 ``alternative_path`` log so the operator can
walk the decision tree post-hoc.

The branch store is SQLite-backed (per-project file) so the cockpit
can keep history when the orchestrator restarts; audit JSONL stays
the authoritative truth for tool calls and Jr replies, the branch
store only carries the conversation tree on top of it.
"""

from selffork_orchestrator.chat.branch_model import Branch, ChatMessage
from selffork_orchestrator.chat.branch_store import BranchStore

__all__ = ["Branch", "BranchStore", "ChatMessage"]
