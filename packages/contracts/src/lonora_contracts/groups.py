from pydantic import Field, model_validator

from .domain import Contract


class GroupCreate(Contract):
    name: str = Field(min_length=1, max_length=80)
    # No cap on how many agents a group holds (mandate P1, 3.3.2).
    member_ids: list[str] = Field(min_length=1)
    participation: str = "mentions_or_lead"
    # What the group is for, shown under its name and searched with it.
    purpose: str = Field(default="", max_length=160)
    # The member that answers when no agent is mentioned.
    lead_agent_id: str | None = None

    @model_validator(mode="after")
    def lead_is_member(self) -> "GroupCreate":
        if self.lead_agent_id is not None and self.lead_agent_id not in self.member_ids:
            raise ValueError("group_lead_not_member")
        return self
