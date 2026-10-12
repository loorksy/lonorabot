from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract

ProviderId = Literal["openai", "anthropic", "deepseek", "zai", "openrouter"]


class Capability(StrEnum):
    CONVERSATION = "conversation"
    REASONING = "reasoning"
    RESEARCH = "research"
    VISION = "vision"
    REALTIME_VOICE = "realtime_voice"
    STT = "stt"
    TTS = "tts"
    BACKGROUND = "background"


class ModelSelection(Contract):
    provider: ProviderId
    model: str = Field(min_length=1, max_length=200)


class RoutingPolicy(Contract):
    mode: Literal["unified", "custom"] = "unified"
    unified: ModelSelection | None = None
    routes: dict[Capability, ModelSelection] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_policy(self) -> "RoutingPolicy":
        if self.mode == "unified" and self.routes:
            raise ValueError("unified_has_custom_routes")
        return self
