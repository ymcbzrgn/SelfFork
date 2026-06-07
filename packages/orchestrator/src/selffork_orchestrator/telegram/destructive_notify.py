"""Destructive-action ↔ Telegram outbound rendering (ADR-006 §4.5).

When the warden opens a :class:`PendingConfirmation`, the store's
``notify_hook`` calls into this module to:

1. Render a Telegram-safe HTML message describing the pending action,
   the workspace, the window, and the inline-keyboard callbacks the
   operator can use to decide ("Approve", "Cancel", "Extend 2h",
   "Ask me").
2. Parse callback_data strings round-tripped through Telegram so the
   PTB ``CallbackQueryHandler`` can translate
   ``pending:approve:<id>`` into a ``PendingConfirmationStore.approve``
   call.

This file is **pure** — no PTB / HTTP imports — so the renderer can be
unit-tested without spinning up the bridge.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Literal, assert_never

from selffork_body.sandbox.pending_confirmations import (
    NotifyOp,
    PendingConfirmation,
)

__all__ = [
    "CALLBACK_PREFIX",
    "CallbackAction",
    "InlineButton",
    "InlineKeyboard",
    "OutboundMessage",
    "build_callback_data",
    "build_message",
    "parse_callback_data",
]


CALLBACK_PREFIX = "pending"
"""Top-level namespace for destructive-action callback_data values."""

CallbackAction = Literal["approve", "cancel", "extend", "ask"]
_VALID_ACTIONS: frozenset[str] = frozenset({"approve", "cancel", "extend", "ask"})


@dataclasses.dataclass(frozen=True, slots=True)
class InlineButton:
    """One Telegram inline-keyboard button (text + callback_data).

    The bridge maps each button into a PTB ``InlineKeyboardButton``;
    keeping a plain dataclass here lets tests assert structure without
    importing PTB.
    """

    text: str
    callback_data: str


@dataclasses.dataclass(frozen=True, slots=True)
class InlineKeyboard:
    """One row of inline buttons (Telegram supports rows of arbitrary length).

    ADR-006 §4.5 example renders a single row with four buttons; we
    keep the shape generic so future categories with custom action
    sets stay easy.
    """

    rows: tuple[tuple[InlineButton, ...], ...]


@dataclasses.dataclass(frozen=True, slots=True)
class OutboundMessage:
    """Rendered notify intent — ready to hand to ``bridge.notify`` or PTB."""

    text: str  # Telegram HTML (already escaped)
    keyboard: InlineKeyboard | None
    level: Literal["info", "warn", "crit"]


def build_callback_data(action: CallbackAction, confirmation_id: str) -> str:
    """Compose ``pending:<action>:<id>`` (Telegram limits payload ≤64 bytes).

    Callers must keep ``confirmation_id`` short. The store mints
    12-char hex ids; including the prefix + action that fits easily.
    """
    if action not in _VALID_ACTIONS:
        msg = f"unknown callback action: {action!r}"
        raise ValueError(msg)
    return f"{CALLBACK_PREFIX}:{action}:{confirmation_id}"


def parse_callback_data(data: str) -> tuple[CallbackAction, str] | None:
    """Extract (action, id) from a callback_data string.

    Returns ``None`` for anything not matching ``pending:<action>:<id>``
    — callers should silently ignore foreign callbacks (other features
    may reuse the inline-keyboard surface later).
    """
    parts = data.split(":", 2)
    if len(parts) != 3:
        return None
    namespace, action, cid = parts
    if namespace != CALLBACK_PREFIX:
        return None
    if action not in _VALID_ACTIONS:
        return None
    if not cid:
        return None
    return action, cid  # type: ignore[return-value]


def _build_keyboard(entry: PendingConfirmation) -> InlineKeyboard:
    return InlineKeyboard(
        rows=(
            (
                InlineButton(
                    text="✅ Approve",
                    callback_data=build_callback_data("approve", entry.id),
                ),
                InlineButton(
                    text="❌ Cancel",
                    callback_data=build_callback_data("cancel", entry.id),
                ),
                InlineButton(
                    text="⏰ Extend 2h",
                    callback_data=build_callback_data("extend", entry.id),
                ),
                InlineButton(
                    text="💬 Ask me",
                    callback_data=build_callback_data("ask", entry.id),
                ),
            ),
        )
    )


def _html_escape(value: str) -> str:
    """Telegram HTML escape — only the documented entities."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_expires(entry: PendingConfirmation) -> str:
    """Human-friendly window summary (``4 hours left → 12:34Z``)."""
    try:
        expires = datetime.fromisoformat(entry.expires_at)
    except ValueError:
        return entry.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    seconds = max(0, int((expires - datetime.now(UTC)).total_seconds()))
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    iso = expires.strftime("%H:%MZ")
    if hours:
        return f"{hours}h {minutes}m left · expires {iso}"
    return f"{minutes}m left · expires {iso}"


def build_message(entry: PendingConfirmation, op: NotifyOp) -> OutboundMessage:
    """Render the appropriate Telegram message for a store event.

    Per ADR-006 §4.5 the headline format is::

        🤖 Self Jr
        Workspace: ...
        Eylem: ...
        Komut: `...`
        Sebep: ...
        Onay penceresi: 4 saat (HH:MMZ'a kadar)

    plus an inline-keyboard row with four buttons. Approval, cancellation,
    expiry, and extension events reuse the same structure with status
    annotations and no buttons (the decision has already been recorded).
    """
    workspace = entry.workspace_slug or "(orphan run)"
    summary = entry.command_summary or "(no summary)"
    reason = entry.category_description or entry.category_id
    expires_line = _format_expires(entry)

    header = "🤖 <b>Self Jr</b>"
    body_lines: list[str]
    keyboard: InlineKeyboard | None
    level: Literal["info", "warn", "crit"]

    if op == "request":
        body_lines = [
            f"<b>Workspace:</b> {_html_escape(workspace)}",
            f"<b>Action:</b> {_html_escape(reason)}",
            f"<b>Command:</b> <code>{_html_escape(summary)}</code>",
            f"<b>Window:</b> {_html_escape(expires_line)}",
            "",
            "<i>Silence past the window = automatic cancel (fail-safe NO).</i>",
        ]
        keyboard = _build_keyboard(entry)
        level = "warn"
    elif op == "approve":
        body_lines = [
            "✅ <b>Approved.</b> Running…",
            f"<b>Workspace:</b> {_html_escape(workspace)}",
            f"<b>Command:</b> <code>{_html_escape(summary)}</code>",
        ]
        keyboard = None
        level = "info"
    elif op == "cancel":
        body_lines = [
            "❌ <b>Cancelled.</b>",
            f"<b>Workspace:</b> {_html_escape(workspace)}",
            f"<b>Command:</b> <code>{_html_escape(summary)}</code>",
        ]
        keyboard = None
        level = "info"
    elif op == "expire":
        body_lines = [
            "⏰ <b>Window expired — action cancelled (silence = NO).</b>",
            f"<b>Workspace:</b> {_html_escape(workspace)}",
            f"<b>Command:</b> <code>{_html_escape(summary)}</code>",
        ]
        keyboard = None
        level = "crit"
    elif op == "extend":
        body_lines = [
            f"⏳ <b>Window extended.</b> New expiry: {_html_escape(expires_line)}",
            f"<b>Workspace:</b> {_html_escape(workspace)}",
            f"<b>Command:</b> <code>{_html_escape(summary)}</code>",
        ]
        keyboard = _build_keyboard(entry)
        level = "info"
    else:
        assert_never(op)

    text = "\n".join([header, "", *body_lines])
    return OutboundMessage(text=text, keyboard=keyboard, level=level)


def flatten_keyboard(keyboard: InlineKeyboard) -> Iterable[InlineButton]:
    """Convenience: iterate buttons in display order."""
    for row in keyboard.rows:
        yield from row
