from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract

# "openai_compatible" is an endpoint the owner names by its base URL (vLLM, Ollama, a
# gateway): an API key and that URL, through the OpenAI-compatible adapter.
ProviderId = Literal["openai", "anthropic", "deepseek", "zai", "openrouter", "openai_compatible"]
# A model provider's key is the owner's workspace secret under the provider's usual
# environment-variable name (lead decision Q14 (b)), the name a command-line tool
# expects (12.2). The router reads it on the server.
PROVIDER_KEY_NAMES: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "zai": "ZAI_API_KEY",
    "openai_compatible": "OPENAI_COMPATIBLE_API_KEY",
}


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


# Text capabilities an Agent's own model serves.
TEXT_CAPABILITIES = (
    Capability.CONVERSATION,
    Capability.REASONING,
    Capability.RESEARCH,
    Capability.BACKGROUND,
    Capability.VISION,
)


class AgentModelChange(AgentModelPreference):
    """The owner's choice for one Agent: its model, or none for the owner's default."""

    expected_revision: int | None = Field(default=None, ge=0)


class AgentModelRecord(Contract):
    owner_id: str
    agent_id: str
    revision: int = Field(default=0, ge=0)
    preference: AgentModelPreference = Field(default_factory=AgentModelPreference)
    # Who set the current choice: the owner (settings, or his message an agent applied),
    # or "inherited" (Lonora's model, copied when the agent was created); None until set.
    chosen_by: Literal["owner", "inherited"] | None = None
    # The agent that applied the owner's message, or Lonora for an inherited model.
    chosen_by_agent_id: str | None = None
    previous: AgentModelPreference | None = None
    changed_at: datetime | None = None
