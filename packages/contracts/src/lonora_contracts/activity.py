"""Owner-visible activity (owner decision Q45): a server projection, never client-made."""

from pydantic import Field

from .domain import Contract


class ActivityEntry(Contract):
    id: str
    code: str = Field(description="What happened, as a stable code the clients label.")
    agent_id: str | None = None
    thread_id: str | None = None
    subject: str = Field(default="", description="The named thing (agent, task, skill).")
    created_at: str
