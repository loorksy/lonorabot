from pydantic import Field

from .domain import Contract


class Reaction(Contract):
    message_id: str
    emoji: str = Field(min_length=1, max_length=16)
