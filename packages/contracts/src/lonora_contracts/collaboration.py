"""Bounded collaboration state; evidence sharing never transfers financial authority."""

from typing import Literal

from pydantic import Field

from .domain import Contract


class CollaborationCreate(Contract):
    subject: str = Field(min_length=1, max_length=8000)
    participant_ids: list[str] = Field(min_length=1, max_length=16)
    session_id: str | None = None


class CollaborationParticipant(Contract):
    agent_id: str
    run_ids: list[str] = Field(default_factory=list, max_length=64)
    status: Literal["invited", "working", "completed", "failed", "cancelled"] = "invited"
    result: str = Field(default="", max_length=30000)
    error_code: str | None = None
    source_message_id: str | None = None
    source_thread_id: str | None = None
    observed_at: str | None = None


class CollaborationRound(Contract):
    id: str
    request_id: str
    host_run_id: str
    subject: str = Field(max_length=8000)
    participant_run_ids: list[str] = Field(default_factory=list[str], max_length=16)
    synthesis_run_id: str | None = None


class CollaborationState(Contract):
    status: Literal["collaborating", "synthesizing", "completed", "cancelled"] = "collaborating"
    participants: list[CollaborationParticipant] = Field(
        default_factory=list[CollaborationParticipant], max_length=16
    )
    rounds: list[CollaborationRound] = Field(default_factory=list[CollaborationRound], max_length=8)
    conflicts: list[str] = Field(default_factory=list, max_length=16)
    final_result: str = Field(default="", max_length=16000)


class CollaborationReference(Contract):
    session_id: str


class CollaborationFinish(CollaborationReference):
    final_result: str = Field(min_length=1, max_length=16000)
    conflicts: list[str] = Field(default_factory=list[str], max_length=16)
