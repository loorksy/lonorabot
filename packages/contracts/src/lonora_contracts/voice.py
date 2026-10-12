from typing import Literal

from pydantic import Field

from .domain import Contract


class VoiceSessionCreate(Contract):
    agent_id: str
    thread_id: str
    mode: Literal["pipeline", "native"] = "pipeline"


class VoiceTranscript(Contract):
    text: str = Field(min_length=1, max_length=30000)
    client_nonce: str
    final: bool = True
