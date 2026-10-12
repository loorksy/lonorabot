from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AgentCreate(Contract):
    name: str = Field(min_length=1, max_length=80)
    avatar: str = "orb"
    color: str = Field(default="#7c83fd", pattern=r"^#[0-9a-fA-F]{6}$")


class AgentUpdate(Contract):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    instructions: str | None = Field(default=None, max_length=16000)
    avatar: str | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    paused: bool | None = None


class ThreadCreate(Contract):
    agent_id: str | None = None
    group_id: str | None = None
    title: str = Field(default="", max_length=160)


class MessageCreate(Contract):
    content: str = Field(min_length=1, max_length=30000)
    client_nonce: str = Field(default_factory=new_id, min_length=1, max_length=80)
    reply_to: str | None = None
    attachment_ids: list[str] = Field(default_factory=list[str], max_length=10)


class ResourceInput(Contract):
    agent_id: str | None = None
    thread_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict[str, Any])


class ResourceUpdate(Contract):
    version: int = Field(ge=1)
    payload: dict[str, Any]


class Board(Contract):
    title: str = Field(min_length=1, max_length=160)
    columns: list[str] = Field(default_factory=lambda: ["todo", "working", "done"])


class Ticket(Contract):
    board_id: str
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=16000)
    status: Literal["todo", "working", "waiting", "done", "failed"] = "todo"
    run_id: str | None = None


class ScratchpadItem(Contract):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(max_length=30000)
