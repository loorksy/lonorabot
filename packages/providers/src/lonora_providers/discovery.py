from lonora_contracts.model_catalog import ModelDescriptor
from lonora_db.client import Database

from .catalog import store_catalog
from .credentials import ProviderCredentials
from .registry import build_adapter, model_adapter


async def discover_models(
    db: Database, credentials: ProviderCredentials, provider: str
) -> list[ModelDescriptor]:
    secret, endpoint = await credentials.connection(provider)
    adapter = build_adapter(model_adapter, provider, secret, endpoint)
    try:
        models = await adapter.discover()
    finally:
        await adapter.close()
    await store_catalog(db, provider, models)
    return models
