"""The owner's own endpoint lists its models: the one provider Lonora asks (VISION 12.4).

Its models are the owner's, so they are read from the endpoint and stored as its
catalog. Every other provider's models are Lonora's fixed list (``catalog``).
"""

from collections.abc import Callable

from lonora_adapter_kit.model import ModelAdapter
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_core.user_error import LonoraError
from lonora_db.client import Database

from .catalog import store_catalog
from .credentials import ProviderCredentials
from .registry import OWNER_ENDPOINT, build_adapter, model_adapter


async def discover_models(
    db: Database,
    credentials: ProviderCredentials,
    provider: str,
    factory: Callable[..., ModelAdapter] = model_adapter,
) -> list[ModelDescriptor]:
    if provider not in OWNER_ENDPOINT:
        raise LonoraError("provider_not_supported", 404)
    secret, endpoint = await credentials.connection(provider)
    adapter = build_adapter(factory, provider, secret, endpoint)
    try:
        models = await adapter.discover()
    finally:
        await adapter.close()
    await store_catalog(db, provider, models)
    return models
