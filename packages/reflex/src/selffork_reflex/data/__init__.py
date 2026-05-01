"""Reflex data pipeline — placeholder until M7.

Will host:
  - Raw export readers (Claude Code JSONL, OpenCode export, ChatGPT export)
  - Normaliser to session-aware chat format (per ``docs/Operator_Locked_Decisions.md``)
  - operator-message detector + filter
  - Sample assembler with full-session-prefix context
"""

from __future__ import annotations
