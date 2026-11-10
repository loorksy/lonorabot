from datetime import datetime
from typing import Any

from pydantic import Field

from .domain import Contract, ThreadOptions, utcnow
from .reactions import MessageReaction


class EventEnvelope(Contract):
    cursor: int = 0
    kind: str
    thread_id: str | None = None
    agent_id: str | None = None
    run_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict[str, Any])
    created_at: datetime = Field(default_factory=utcnow)


class MessageReactionUpdated(Contract):
    """``message.reaction_updated``: the message's whole reaction list after a change."""

    thread_id: str
    message_id: str
    reactions: list[MessageReaction]


class ThreadUpdated(Contract):
    """``thread.updated``: the chat's options after ``PUT /api/threads/{id}/options``."""

    thread_id: str
    options: ThreadOptions
