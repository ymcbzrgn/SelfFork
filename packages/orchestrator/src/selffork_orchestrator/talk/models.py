"""Pydantic domain models for the Talk conversation store — S1.

Talk is the operator ↔ Self Jr conversation surface. A conversation is a
flat thread (no branching); message ordering relies on the monotonic
per-conversation ``seq``, never on ``created_at`` — two messages can land
in the same millisecond.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

__all__ = ["Conversation", "TalkMessage", "TalkRole"]


TalkRole = Literal["operator", "self_jr"]


class Conversation(BaseModel):
    """One operator ↔ Self Jr conversation thread.

    ``workspace_slug`` scopes the conversation to a project; ``None`` is a
    global conversation not tied to any workspace. ``last_message_at`` is
    denormalised so the conversation list sorts without a join against
    ``messages``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    workspace_slug: str | None
    title: str
    created_at: datetime
    last_message_at: datetime


class TalkMessage(BaseModel):
    """One message in a conversation.

    ``seq`` is a per-conversation monotonic counter starting at 1; thread
    ordering relies on it, not on ``created_at``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    conversation_id: UUID
    seq: int
    role: TalkRole
    content: str
    created_at: datetime
