from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract


class SkillActivation(Contract):
    mode: Literal["automatic", "explicit", "trigger_based"] = "automatic"
    intents: list[str] = Field(default_factory=list, max_length=32)
    triggers: list[str] = Field(default_factory=list, max_length=32)


class SkillManifest(Contract):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    version: str = Field(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1000)
    source: Literal["builtin", "owner", "installed", "external", "legacy"] = "owner"
    stability: Literal["stable", "experimental", "legacy"] = "stable"
    activation: SkillActivation = Field(default_factory=SkillActivation)
    risk_class: Literal["read_only", "state_mutating", "external_action", "financial"] = "read_only"
    required_capabilities: list[str] = Field(default_factory=list, max_length=32)
    required_tools: list[str] = Field(default_factory=list, max_length=64)
    dependencies: list[str] = Field(default_factory=list, max_length=32)
    conflicts: list[str] = Field(default_factory=list, max_length=32)
    priority: int = Field(default=50, ge=0, le=100)
    context_budget: int = Field(default=6000, ge=128, le=16000)


class AgentSkill(Contract):
    name: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=16000)
    enabled: bool = True
    manifest: SkillManifest | None = None

    @model_validator(mode="after")
    def manifest_identity(self) -> "AgentSkill":
        if self.manifest and (self.manifest.id != self.name or self.manifest.source == "builtin"):
            raise ValueError("skill_manifest_identity_invalid")
        return self


class PlaybookManifest(Contract):
    """Describes an existing domain workflow; never creates a second workflow executor."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    version: str = Field(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
    required_skills: list[str] = Field(min_length=1, max_length=16)
    required_tools: list[str] = Field(min_length=1, max_length=32)
    state_owner: str = Field(min_length=1, max_length=256)
    entry_conditions: list[str] = Field(min_length=1, max_length=16)
    terminal_states: list[str] = Field(min_length=1, max_length=16)
    recovery: str = Field(min_length=1, max_length=1000)
