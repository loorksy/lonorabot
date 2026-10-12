from pydantic import Field

from .domain import Contract
from .model_routing import ProviderId


class ModelDescriptor(Contract):
    id: str
    provider: ProviderId
    name: str
    capabilities: list[str] = Field(default_factory=list)
    verified: bool = False
    context_window: int | None = None
    source: str


class ProviderCredential(Contract):
    api_key: str = Field(min_length=8, max_length=4096)
