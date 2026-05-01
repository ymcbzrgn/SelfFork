"""Parser for ``<selffork-tool-call>`` JSON blocks in Jr's replies.

Wire format (per ``project_jr_tool_protocol.md``)::

    <selffork-tool-call>
    {
      "tool": "kanban_card_move",
      "args": {"card_id": "card-...", "to_column": "done"}
    }
    </selffork-tool-call>

- Multiple blocks per reply are allowed; each becomes a separate
  :class:`ToolCall` with ``order_in_reply`` matching its position.
- Whitespace inside the block is ignored (JSON parser handles it).
- Malformed blocks (non-JSON, missing ``tool``, missing ``args``) are
  silently skipped — small models drift; we want graceful degradation
  rather than a crash. Skipped blocks log at debug level so we can
  diagnose without spamming.
- Case-insensitive matching on the tag name (``<SelfFork-Tool-Call>``
  also works) — small models love title-casing things.
"""

from __future__ import annotations

import json
import re

from selffork_orchestrator.tools.base import ToolCall
from selffork_shared.logging import get_logger

__all__ = ["parse_tool_calls"]

_log = get_logger(__name__)

# DOTALL so the JSON body may span multiple lines.
_BLOCK_RE = re.compile(
    r"<selffork-tool-call>\s*(.*?)\s*</selffork-tool-call>",
    re.IGNORECASE | re.DOTALL,
)


def parse_tool_calls(reply: str) -> list[ToolCall]:
    """Extract every ``<selffork-tool-call>`` block from ``reply``.

    Returns an empty list when there are none. Never raises.
    """
    if not reply or "<selffork-tool-call>" not in reply.lower():
        return []
    out: list[ToolCall] = []
    for i, match in enumerate(_BLOCK_RE.finditer(reply)):
        body = match.group(1).strip()
        if not body:
            continue
        try:
            obj = json.loads(body)
        except json.JSONDecodeError as exc:
            _log.debug("tool_call_skip_malformed_json", error=str(exc))
            continue
        if not isinstance(obj, dict):
            _log.debug("tool_call_skip_non_object", got=type(obj).__name__)
            continue
        tool = obj.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            _log.debug("tool_call_skip_missing_tool")
            continue
        args = obj.get("args")
        if not isinstance(args, dict):
            args = {}
        out.append(ToolCall(tool=tool.strip(), args=args, order_in_reply=i))
    return out
