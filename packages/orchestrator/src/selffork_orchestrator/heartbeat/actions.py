"""Heartbeat action vocabulary — closed enum of 10 outer-loop actions.

ADR-008 §4.4: the action vocabulary is **closed** (no arbitrary actions)
so the audit log + Settings panel + deliberative model can reason about
it categorically. Faz B uses these as keys in the
:class:`selffork_orchestrator.heartbeat.filter.LegalActionFilter` output;
Faz D adds per-action executors.

Names are ASCII (PEP 8); values are the operator-facing Turkish labels
from the ADR — the model sees the values, the code touches the names.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["LegalAction"]


class LegalAction(StrEnum):
    """One of the 10 closed outer-loop action labels (ADR-008 §4.4 + ADR-010 §4).

    Order matches the ADR-008 §4.4 + ADR-010 §4 tables. ``BODY_USE`` and
    ``BODY_REVIEW`` were added by S-Vision (ADR-010 §4) to give the model
    a granular hook for the Body pillar (write/click/screenshot vs.
    read-only vision parse) — distillation-friendly for M7 + auditable.
    Adding an action requires a coordinated change across ADR-008/010,
    this enum, and the rules in :class:`LegalActionFilter`.
    """

    TASK_START = "task_başlat"
    SESSION_RESUME = "session_devam"
    CLI_SELECT = "cli_seç"
    KANBAN_SUGGEST = "kanban_task_öner"
    OPERATOR_ASK = "operatöre_sor"
    IDEATE = "fikirleş"
    BODY_USE = "uzvunu_kullan"
    BODY_REVIEW = "uzvunu_incele"
    WAIT = "bekle"
    SELF_STOP = "kendini_durdur"
