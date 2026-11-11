"""Quick reactions on messages (Q26, Q28): six fixed emojis, one per reactor and message.

A reactor is the owner (``"owner"``) or an agent (its id). The same list lives in TypeScript
as ``REACTION_EMOJIS``.
"""

from datetime import datetime
from typing import Final

from pydantic import Field

from .domain import Contract

REACTION_EMOJIS: Final = ("👍", "❤️", "😂", "😮", "😢", "🙏")
OWNER_REACTOR: Final = "owner"


class Reaction(Contract):
    message_id: str
    emoji: str = Field(min_length=1, max_length=16)


class MessageReaction(Contract):
    reactor: str = Field(min_length=1, max_length=36)
    emoji: str = Field(min_length=1, max_length=16)
    created_at: datetime


class MessageReactions(Contract):
    """The answer of the reaction routes and the ``message.reaction_updated`` payload
    (which also carries ``thread_id``)."""

    message_id: str
    reactions: list[MessageReaction]
