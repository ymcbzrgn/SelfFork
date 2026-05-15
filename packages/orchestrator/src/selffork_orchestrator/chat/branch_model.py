"""Pydantic domain models for the chat branch store — Order 4."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

__all__ = ["Branch", "ChatMessage", "MessageRole"]


MessageRole = Literal["user", "assistant", "tool"]


class Branch(BaseModel):
    """One conversation thread within a session.

    ``parent_branch_id`` + ``fork_message_id`` together form the
    branch tree: a fork copies all messages up to and including
    ``fork_message_id`` from the parent, then accepts new messages
    independently. ``is_active`` is the cockpit's currently-shown
    thread; switching active branches is a single ``PATCH`` away.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    session_id: str
    parent_branch_id: UUID | None
    fork_message_id: UUID | None
    label: str
    is_active: bool
    created_at: datetime


class ChatMessage(BaseModel):
    """One message on a branch.

    ``parent_message_id`` is the previous message on the same branch
    (so replays keep order even if the DB returns rows out of insert
    order). ``role`` mirrors the standard chat schema; ``tool`` is
    used for inline tool-result echoes that aren't fully audit-only
    (rare — most tool calls live entirely in the audit JSONL).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    branch_id: UUID
    role: MessageRole
    content: str
    parent_message_id: UUID | None
    created_at: datetime
