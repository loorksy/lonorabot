from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, cast

from pydantic import Field, model_validator

from .domain import Contract

# "openai_compatible" is an endpoint the owner names by its base URL (vLLM, Ollama, a
# gateway): an API key and that URL, through the OpenAI-compatible adapter.
ProviderId = Literal["openai", "anthropic", "deepseek", "zai", "openrouter", "openai_compatible"]
# A model provider's key is the owner's workspace secret under the provider's usual
# environment-variable name (lead decision Q14 (b)): the router reads it on the server,
# and a tool an agent runs in the workspace finds it under the name it expects (12.2).
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


# "automatic": Lonora chooses. The Agent starts on the owner's default model and may
# switch itself among the owner's allowed models. "fixed": the owner chose one model;
# only the owner changes it (an Agent's own request becomes an owner card).
AgentModelMode = Literal["automatic", "fixed"]
# Text capabilities an Agent's own model serves; their global routes are allowed models.
TEXT_CAPABILITIES = (
    Capability.CONVERSATION,
    Capability.REASONING,
    Capability.RESEARCH,
    Capability.BACKGROUND,
    Capability.VISION,
)
MAXIMUM_ADDED_MODELS = 20


def legacy_mode(data: Any) -> Any:
    """Records and requests written before modes existed: a stored primary was the
    owner's own choice, so it reads as Fixed; none reads as Automatic."""
    if not isinstance(data, dict):
        return data
    values = cast(dict[str, Any], data)
    if "mode" in values:
        return values
    preference: Any = values.get("preference", values)
    primary: Any = (
        cast(dict[str, Any], preference).get("primary") if isinstance(preference, dict) else None
    )
    return {**values, "mode": "fixed" if primary else "automatic"}


class AgentModelChange(AgentModelPreference):
    """The owner's choice for one Agent. Fixed needs its model; Automatic may name a
    starting model the Agent can later change."""

    mode: AgentModelMode = "automatic"
    expected_revision: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def unset_mode(cls, data: Any) -> Any:
        return legacy_mode(data)

    @model_validator(mode="after")
    def fixed_has_model(self) -> "AgentModelChange":
        if self.mode == "fixed" and self.primary is None:
            raise ValueError("agent_model_fixed_requires_model")
        return self


class AgentModelState(Contract):
    """A mode and its models: what Undo restores."""

    mode: AgentModelMode = "automatic"
    preference: AgentModelPreference = Field(default_factory=AgentModelPreference)


class AgentModelRecord(Contract):
    owner_id: str
    agent_id: str
    revision: int = Field(default=0, ge=0)
    mode: AgentModelMode = "automatic"
    preference: AgentModelPreference = Field(default_factory=AgentModelPreference)
    # Who made the current choice; None until anyone chose.
    chosen_by: Literal["owner", "agent"] | None = None
    # The Agent that switched itself (or switched on the owner's request).
    chosen_by_agent_id: str | None = None
    previous: AgentModelState | None = None
    changed_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def unset_mode(cls, data: Any) -> Any:
        return legacy_mode(data)

    def state(self) -> AgentModelState:
        return AgentModelState(mode=self.mode, preference=self.preference)


class AllowedModels(Contract):
    """Models the owner allowed beyond the global routes and backups. Agents switch
    among the whole allowed list on their own; any other model is an owner card."""

    added: list[ModelSelection] = Field(
        default_factory=list[ModelSelection], max_length=MAXIMUM_ADDED_MODELS
    )

    @model_validator(mode="after")
    def distinct_models(self) -> "AllowedModels":
        if len({(item.provider, item.model) for item in self.added}) != len(self.added):
            raise ValueError("agent_model_duplicate")
        return self
