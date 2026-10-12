from datetime import datetime
from typing import Any

from pydantic import Field

from .domain import Contract, utcnow


class EventEnvelope(Contract):
    cursor: int = 0
    kind: str
    thread_id: str | None = None
    agent_id: str | None = None
    run_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict[str, Any])
    created_at: datetime = Field(default_factory=utcnow)
