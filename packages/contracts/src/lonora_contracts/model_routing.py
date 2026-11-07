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
    routes: dict[Capability, ModelSelection] = Field(
        default_factory=dict[Capability, ModelSelection]
    )

    @model_validator(mode="after")
    def validate_policy(self) -> "RoutingPolicy":
        if self.mode == "unified" and any(
            capability not in {Capability.STT, Capability.TTS, Capability.REALTIME_VOICE}
            for capability in self.routes
        ):
            raise ValueError("unified_has_custom_routes")
        return self


class AgentModelPreference(Contract):
    """Owner-chosen models for one Agent, tried before the global routes.

    Choosing a model never grants authority: permissions, financial approval
    and every execution boundary stay with the Agent, whatever model answers.
    """

    primary: ModelSelection | None = None
    fallbacks: list[ModelSelection] = Field(default_factory=list[ModelSelection], max_length=3)

    @model_validator(mode="after")
    def distinct_models(self) -> "AgentModelPreference":
        chosen = ([self.primary] if self.primary else []) + self.fallbacks
        if len({(item.provider, item.model) for item in chosen}) != len(chosen):
            raise ValueError("agent_model_duplicate")
        return self


class AgentModelChange(AgentModelPreference):
    expected_revision: int | None = Field(default=None, ge=0)


class AgentModelRecord(Contract):
    owner_id: str
    agent_id: str
    revision: int = Field(default=0, ge=0)
    preference: AgentModelPreference = Field(default_factory=AgentModelPreference)
