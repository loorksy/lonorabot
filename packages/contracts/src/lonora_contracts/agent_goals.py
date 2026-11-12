"""Light goals of an agent that does not trade (owner decision Q41).

A light goal is a note the owner keeps for an agent: a title, a description and whether
it is done. It schedules nothing and grants no autonomy or authority (W15-9).
"""

from pydantic import Field

from .domain import Contract


class AgentGoal(Contract):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    done: bool = False
