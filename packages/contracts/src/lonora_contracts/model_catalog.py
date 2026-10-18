from pydantic import Field

from .domain import Contract
from .model_routing import ProviderId


class ModelDescriptor(Contract):
    id: str
    provider: ProviderId
    name: str
    capabilities: list[str] = Field(default_factory=list[str])
    verified: bool = False
    context_window: int | None = Field(default=None, gt=0)
    maximum_output_tokens: int | None = Field(default=None, gt=0)
    source: str


class ProviderCredential(Contract):
    api_key: str = Field(min_length=8, max_length=4096)
