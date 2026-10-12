from pydantic import Field

from .domain import Contract


class AgentSkill(Contract):
    name: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=16000)
    enabled: bool = True
