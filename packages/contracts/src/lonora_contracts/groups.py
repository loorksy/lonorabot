from pydantic import Field

from .domain import Contract


class GroupCreate(Contract):
    name: str = Field(min_length=1, max_length=80)
    member_ids: list[str] = Field(min_length=1, max_length=12)
    participation: str = "mentions_or_lead"
