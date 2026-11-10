from typing import Literal

from pydantic import Field

from .domain import Contract


class VoiceSessionCreate(Contract):
    agent_id: str
    thread_id: str
    mode: Literal["gpt_live"] = "gpt_live"
    sdp: str = Field(min_length=1, max_length=65536)
    client_nonce: str = Field(min_length=1, max_length=80)
    # The agent's incoming call the owner accepted and now answers: the call is linked to
    # it explicitly, so its bubble is incoming (never guessed from timing).
    incoming_call_id: str | None = Field(default=None, min_length=1, max_length=36)


class VoiceTranscript(Contract):
    text: str = Field(min_length=1, max_length=30000)
    client_nonce: str
    final: bool = True


class VoiceInitCancel(Contract):
    client_nonce: str = Field(min_length=1, max_length=80)
